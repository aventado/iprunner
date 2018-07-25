#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/7/23 19:25
# @Author  : ganliang
# @File    : TaskManager.py
# @Desc    : 任务管理


import logging
import time

from TaskAssign import TaskAssign
from src.config.RedisConfig import RedisConfig
from src.config.TaskConfig import TaskConfig

logging.basicConfig(**TaskConfig.LOGGING_CONFIG)


class TaskManager:
    """任务管理器"""

    def __init__(self, runingTaskCount=1, everyTaskThreadCount=3):
        self.runingTaskCount = runingTaskCount
        self.everyTaskThreadCount = everyTaskThreadCount
        self.taskContainer = {}  # 任务的容器
        self.taskThreads = []  # 没执行一个任务 保存线程
        logging.info("任务管理器初始化完毕，最多可同时运行的任务数量：[ %s ] 每个任务的线程数量: [ %s ]" % (self.runingTaskCount, everyTaskThreadCount))

    def completeTaskAssign(self, taskAssign, result=True):
        """完成任务的分配"""
        if taskAssign in self.taskThreads:
            connection = RedisConfig().connection()
            self.taskThreads.remove(taskAssign)
            self.taskContainer.pop(taskAssign.taskInstanceId)

            ports = taskAssign.taskInfo["ports"]
            if result:
                logging.info("任务管理器-任务完成 [ %s ]" % taskAssign.taskInstanceId)

                # 判断任务是否全部完成
                counter = connection.decr(TaskConfig.TASK_INSTANCE_COUNTER_PREFIX + str(taskAssign.taskInstanceId),
                                          len(ports))
                if counter <= 0:
                    connection.lrem(TaskConfig.TASK_INSTANCE_QUEUE, 0, taskAssign.taskInstanceId)
                    logging.info("任务管理器-任务 [ %s ] 全部完成" % taskAssign.taskInstanceId)
            else:
                if len(ports) > 0:
                    connection.lpush(TaskConfig.TASK_INSTANCE_PORT_PREFIX + str(taskAssign.taskInstanceId), *ports)
                    logging.info("任务管理器-任务出错，将端口列表数据回滚")
                else:
                    logging.info("任务管理器-任务出错，端口数据不存在")
        else:
            logging.info("任务管理器-任务不存在 [ %s ]" % taskAssign.taskInstanceId)

    def queryTaskInfo(self, taskInstanceId):
        """通过数据库查询任务的详细信息"""
        taskInfo = {
            "taskId": taskInstanceId,
            "taskInstanceId": taskInstanceId,
            "protocol": "udp",
            "createTime": "2018-07-25 13:03:20",
            "ports": []
        }
        return taskInfo

    def lookupTask(self):
        """从redis中可运行的查询任务"""

        # 判断该任务管理器是否已经满了 如果满载 则退出任务管理
        if len(self.taskContainer) == self.runingTaskCount:
            logging.info("任务管理器中的任务已经满载,任务管理器挂起！")
            return

        connection = RedisConfig().connection()
        # 从redis中获取到所有的任务
        taskInstances = connection.lrange(TaskConfig.TASK_INSTANCE_QUEUE, 0, -1)
        if len(taskInstances) > 0:
            for taskInstanceId in taskInstances:
                # 判断该任务是否已经在执行了 如果已经在执行了 则过滤该任务
                if taskInstanceId in self.taskContainer.keys():
                    logging.info("任务管理器-任务正在执行，请稍等....")
                    continue
                # 判断该任务管理器是否已经满了 如果满载 则退出任务管理
                if len(self.taskContainer) == self.runingTaskCount:
                    logging.info("任务管理器-任务管理器中的任务已经满载,任务挂起！")
                    break
                # 根据任务实例id查询数据库
                taskInfo = self.queryTaskInfo(taskInstanceId)

                # 执行任务 开启一个新的线程 该线程主要分配该任务的分配 包括ip、端口号的获取 实际执行线程的数量
                logging.info("任务管理器-执行任务分配器任务 [ %s ]" % taskInstanceId)
                taskAssign = TaskAssign(self, taskInfo, self.everyTaskThreadCount)
                taskAssign.start()

                # 保存任务信息
                self.taskContainer.setdefault(taskInstanceId, taskInfo)
                self.taskThreads.append(taskAssign)
        else:
            logging.info("任务管理器-没有扫描到任务")

    def executeTaskManager(self):
        """执行任务管理器"""

        # 循环扫描任务
        while True:
            self.lookupTask()
            time.sleep(60)

            # 如果任务管理器任务已经满载 则停止接收任务 等待任务完成
            if len(self.taskThreads) == self.runingTaskCount:
                for taskAssign in self.taskThreads:
                    taskAssign.join()
                    # 待一半的任务已经执行完毕 则结束任务等待
                    if len(self.taskThreads) <= self.runingTaskCount // 2:
                        break


if __name__ == "__main__":
    pass
