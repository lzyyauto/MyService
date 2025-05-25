from typing import Optional

import aiohttp


class BarkService:

    def __init__(self,
                 base_url: str,
                 default_device_key: Optional[str] = None):
        """
        初始化 Bark 服务
        
        Args:
            base_url: Bark 服务器地址，例如 https://api.day.app
            default_device_key: 默认设备 key
        """
        self.base_url = base_url.rstrip('/')
        self.default_device_key = default_device_key

    async def send_notification(
        self,
        title: str,
        content: str,
        device_key: Optional[str] = None,
        level: str = "timeSensitive",  # active, timeSensitive, passive
        sound: Optional[str] = None,
        icon: Optional[str] = None,
        group: Optional[str] = None,
        url: Optional[str] = None,
        copy: Optional[str] = None,
        badge: Optional[int] = None,
        is_archive: bool = True,
    ) -> bool:
        """
        发送 Bark 通知
        
        Args:
            title: 通知标题
            content: 通知内容
            device_key: 设备 key，如果不提供则使用默认值
            level: 通知级别
            sound: 提示音
            icon: 图标 URL
            group: 通知分组
            url: 点击通知跳转的 URL
            copy: 点击通知复制的文本
            badge: 角标数字
            is_archive: 是否归档
            
        Returns:
            发送是否成功
        """
        device_key = device_key or self.default_device_key
        if not device_key:
            raise ValueError("device_key is required")

        # 构建请求 URL
        url = f"{self.base_url}/{device_key}/{title}/{content}"

        # 构建查询参数
        params = {
            "level": level,
            "isArchive": "1" if is_archive else "0",
        }
        if sound:
            params["sound"] = sound
        if icon:
            params["icon"] = icon
        if group:
            params["group"] = group
        if url:
            params["url"] = url
        if copy:
            params["copy"] = copy
        if badge is not None:
            params["badge"] = str(badge)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    return response.status == 200
        except Exception as e:
            print(f"Bark 通知发送失败: {str(e)}")
            return False

    async def send_rest_notification(self,
                                     device_key: str,
                                     rest_type: int,
                                     location: Optional[str] = None) -> bool:
        """
        发送休息记录通知
        
        Args:
            device_key: 设备 key
            rest_type: 休息类型（0-睡眠，1-起床）
            location: 位置信息
            
        Returns:
            发送是否成功
        """
        title = "睡眠提醒" if rest_type == 0 else "起床提醒"
        content = f"记录{'睡眠' if rest_type == 0 else '起床'}时间"
        if location:
            content += f"\n位置：{location}"

        return await self.send_notification(title=title,
                                            content=content,
                                            device_key=device_key,
                                            level="timeSensitive",
                                            sound="bell",
                                            group="rest_records")

    async def send_task_notification(self, device_key: str, task_name: str,
                                     status: int, priority: int) -> bool:
        """
        发送任务状态变更通知
        
        Args:
            device_key: 设备 key
            task_name: 任务名称
            status: 任务状态
            priority: 任务优先级
            
        Returns:
            发送是否成功
        """
        status_map = {0: "待办", 1: "进行中", 2: "已完成", 3: "已取消"}

        title = f"任务状态更新：{status_map[status]}"
        content = f"任务：{task_name}\n优先级：{priority}"

        return await self.send_notification(
            title=title,
            content=content,
            device_key=device_key,
            level="active" if priority >= 8 else "timeSensitive",
            sound="bell",
            group="gtd_tasks")
