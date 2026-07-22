# -*- coding: utf-8 -*-
import json
import logging
import os
import sys

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkecs.request.v20140526 import (
    DescribeInstancesRequest,
    StartInstancesRequest,
    StopInstancesRequest,
)

# ================== 1. 配置日志 ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ================== 2. 从环境变量获取配置 ==================
ACCESS_KEY_ID = os.getenv("ALIYUN_ACCESS_KEY_ID")
ACCESS_KEY_SECRET = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
REGION_ID = os.getenv("ALIYUN_REGION_ID", "cn-hongkong")
ECS_INSTANCE_ID = os.getenv("ALIYUN_ECS_INSTANCE_ID")
TRAFFIC_THRESHOLD_GB = float(os.getenv("TRAFFIC_THRESHOLD_GB", "180"))

if not ACCESS_KEY_ID or not ACCESS_KEY_SECRET or not ECS_INSTANCE_ID:
    logger.error("缺少必要的环境变量，请检查 Secrets 配置！")
    sys.exit(1)

# ================== 3. 初始化客户端 ==================
try:
    client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, REGION_ID)
    logger.info("AcsClient 初始化成功。")
except Exception as e:
    logger.error(f"初始化 AcsClient 失败: {e}")
    sys.exit(1)


# ================== 4. 查询当前总流量 ==================
def get_total_traffic_gb(client):
    request = CommonRequest()
    request.set_domain("cdt.aliyuncs.com")
    request.set_version("2021-08-13")
    request.set_action_name("ListCdtInternetTraffic")
    request.set_method("POST")

    try:
        response = client.do_action_with_exception(request)
        response_json = json.loads(response.decode("utf-8"))

        total_bytes = sum(
            d.get("Traffic", 0)
            for d in response_json.get("TrafficDetails", [])
        )
        total_gb = total_bytes / (1024**3)

        logger.info(f"当前总互联网流量: {total_gb:.2f} GB")
        return total_gb
    except Exception as e:
        logger.error(f"获取 CDT 流量失败: {e}")
        sys.exit(1)


# ================== 5. 查询 ECS 实例状态 ==================
def get_ecs_status(client, instance_id):
    try:
        request = DescribeInstancesRequest.DescribeInstancesRequest()
        request.set_InstanceIds([instance_id])
        response = client.do_action_with_exception(request)
        response_json = json.loads(response.decode("utf-8"))

        instances = response_json.get("Instances", {}).get("Instance", [])
        if not instances:
            logger.error("未找到该 ECS 实例信息。")
            return None

        status = instances[0].get("Status")
        logger.info(f"ECS 实例 {instance_id} 当前状态: {status}")
        return status
    except Exception as e:
        logger.error(f"获取 ECS 实例状态失败: {e}")
        return None


# ================== 6. 启动 ECS 实例 ==================
def ecs_start(client, instance_id):
    status = get_ecs_status(client, instance_id)
    if status == "Running":
        logger.info(f"ECS 实例 {instance_id} 已经是运行状态，无需启动。")
        return

    try:
        request = StartInstancesRequest.StartInstancesRequest()
        request.set_InstanceIds([instance_id])
        request.set_accept_format("json")

        response = client.do_action_with_exception(request)
        logger.info(f"ECS 启动响应: {response.decode('utf-8')}")
    except Exception as e:
        logger.error(f"启动 ECS 实例失败: {e}")


# ================== 7. 停止 ECS 实例 ==================
def ecs_stop(client, instance_id):
    status = get_ecs_status(client, instance_id)
    if status == "Stopped":
        logger.info(f"ECS 实例 {instance_id} 已经是停止状态，无需再次停止。")
        return

    try:
        request = StopInstancesRequest.StopInstancesRequest()
        request.set_InstanceIds([instance_id])
        request.set_ForceStop(False)
        request.set_accept_format("json")

        response = client.do_action_with_exception(request)
        logger.info(f"ECS 停止响应: {response.decode('utf-8')}")
    except Exception as e:
        logger.error(f"停止 ECS 实例失败: {e}")


# ================== 8. 主流程 ==================
def main():
    total_gb = get_total_traffic_gb(client)

    if total_gb < TRAFFIC_THRESHOLD_GB:
        logger.info(
            f"流量 {total_gb:.2f} GB < 阈值 {TRAFFIC_THRESHOLD_GB} GB，尝试启动 ECS"
        )
        ecs_start(client, ECS_INSTANCE_ID)
    else:
        logger.info(
            f"流量 {total_gb:.2f} GB ≥ 阈值 {TRAFFIC_THRESHOLD_GB} GB，尝试停止 ECS"
        )
        ecs_stop(client, ECS_INSTANCE_ID)

    logger.info("脚本执行完毕。")


if __name__ == "__main__":
    main()
