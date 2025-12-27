"""
AI客户端抽象层
支持多种AI服务切换（硅基AI、OpenAI等）
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings


class AIClient(ABC):
    """AI客户端抽象基类"""

    @abstractmethod
    async def recognize_speech(self, audio_path: Path) -> str:
        """语音识别 - 将音频转换为文字"""
        pass

    @abstractmethod
    async def summarize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """文本总结 - 对字幕进行总结和精简"""
        pass


class SiliconFlowClient(AIClient):
    """硅基AI客户端 - 使用OpenAI兼容格式"""

    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.base_url = "https://api.siliconflow.cn/v1"
        self.voice_model = getattr(settings, 'AI_VOICE_MODEL', 'Qwen/QwQ-32B')
        self.summary_model = getattr(settings, 'AI_SUMMARY_MODEL', 'Qwen/QwQ-32B')
        self.timeout = 300  # 5分钟超时

    async def recognize_speech(self, audio_path: Path) -> str:
        """
        语音识别 - 使用硅基AI的语音识别能力
        硅基AI使用 multipart/form-data 格式上传文件
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(audio_path, 'rb') as f:
                    files = {'file': (audio_path.name, f, 'audio/mpeg')}
                    data = {
                        'model': 'FunAudioLLM/SenseVoiceSmall'
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}"
                    }

                    response = await client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers=headers,
                        data=data,
                        files=files
                    )

                if response.status_code == 200:
                    result = response.json()
                    # 硅基AI返回的是包含text字段的JSON
                    return result.get('text', '') or result.get('result', '') or ''
                else:
                    raise Exception(f"语音识别失败: {response.status_code} - {response.text}")

        except Exception as e:
            raise Exception(f"硅基AI语音识别失败: {str(e)}")

    async def summarize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """
        文本总结 - 使用硅基AI对字幕进行总结和精简
        """
        try:
            # 构建总结提示词
            prompt = f"""

            角色: 你是一个专业的短视频内容分析师。你的唯一目标是成为视频的“文字复现版”，帮助用户在不观看视频的情况下，获取其中所有的核心信息、论据和细节。

核心任务: 你必须按时间顺序，详细、完整地复述视频的“讲述内容”。你的输出必须包含视频中的所有关键事实、观点、原因和示例。

工作流程与输出格式 (统一模板):

【核心主题】: [用一句话高度概括这个视频是关于什么的]

【视频结论 (一句话速览)】: [把视频作者最后得出的核心结论、最终建议或关键成果，立刻放在这里。]

【视频详细拆解 (按讲述顺序)】: [这是最重要的部分。你必须像“同声传译”一样，把视频的讲述逻辑和关键内容一步步写下来。]

1. [开场/引入]:

[视频是如何开始的？它提出了什么问题、展示了什么场景、或设定了什么背景？]

2. [核心内容 - 展开 (第一部分)]:

[接着，视频展示或讲述了什么？]

[关键事实/观点]: [作者提出的第一个主要论点、事实、或展示的第一步操作。]

[支撑信息/细节]: [支持这个观点的原因、数据、示例、详细描述，或者是这步操作的具体做法、用料、参数。]

3. [核心内容 - 展开 (第二部分)]:

[视频的下一个步骤或论点是什么？]

[关键事实/观点]: [第二个主要论点、事实、或第二步操作。]

[支撑信息/细节]: [同上，提供与“关键事实2”配套的原因、示例、做法、数据等。]

4. [核心内容 - 展开 (第 N 部分)]:

(根据视频长度，Agent应自行重复这个“展开”结构，直到内容结束)

5. [结尾/总结]:

[视频是如何收尾的？作者重申了什么观点，或者给出了什么最终的建议/成品展示？]

【视频类型】: [例如：知识科普 / 产品评测 / 避坑指南 / 技能教程 / 生活Vlog / 观点输出]

约束条件:

拒绝“骨架”: 你的价值在于提供“血肉”。不要只说“他提到了A”，而要说**“他提到A，A的内容是B，原因是C，具体做法是D”**。

忠实复述: 严格基于视频内容，不要自己编造或联想。你的目标就是成为视频的“文字版”。
            
            原文如下：

{text}

要求：
1. 提取关键信息、要点和核心内容
2. 保留重要的细节和数据
3. 保持逻辑清晰，结构化呈现
4. 如果可能，提取出可操作的建议或结论
5. 用简洁的中文表达

总结："""

            if max_length:
                prompt += f"\n（请控制在{max_length}字以内）"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.summary_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2000
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"文本总结失败: {response.status_code} - {response.text}")

        except Exception as e:
            raise Exception(f"硅基AI文本总结失败: {str(e)}")


class OpenAIClient(AIClient):
    """OpenAI客户端 - 便于切换到OpenAI服务"""

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else ""
        self.base_url = "https://api.openai.com/v1"
        self.voice_model = "whisper-1"
        self.summary_model = "gpt-4"
        self.timeout = 300

    async def recognize_speech(self, audio_path: Path) -> str:
        """OpenAI语音识别 - 使用 multipart/form-data 格式"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(audio_path, 'rb') as f:
                    files = {'file': (audio_path.name, f, 'audio/mpeg')}
                    data = {
                        'model': self.voice_model,
                        'response_format': 'text',
                        'language': 'zh'
                    }
                    headers = {
                        "Authorization": f"Bearer {self.api_key}"
                    }

                    response = await client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers=headers,
                        data=data,
                        files=files
                    )

                if response.status_code == 200:
                    return response.text
                else:
                    raise Exception(f"OpenAI语音识别失败: {response.status_code} - {response.text}")

        except Exception as e:
            raise Exception(f"OpenAI语音识别失败: {str(e)}")

    async def summarize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """OpenAI文本总结"""
        try:
            prompt = f"""请对以下视频字幕进行总结和精简：

{text}

要求：
1. 提取关键信息、要点和核心内容
2. 保留重要的细节和数据
3. 保持逻辑清晰，结构化呈现
4. 如果可能，提取出可操作的建议或结论
5. 用简洁的中文表达

总结："""

            if max_length:
                prompt += f"\n（请控制在{max_length}字以内）"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.summary_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 2000
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"OpenAI文本总结失败: {response.status_code} - {response.text}")

        except Exception as e:
            raise Exception(f"OpenAI文本总结失败: {str(e)}")


# AI客户端工厂
def get_ai_client() -> AIClient:
    """
    获取AI客户端实例
    根据配置自动选择使用硅基AI或OpenAI
    """
    ai_provider = getattr(settings, 'AI_PROVIDER', 'siliconflow').lower()

    if ai_provider == 'siliconflow':
        if not settings.SILICONFLOW_API_KEY:
            raise ValueError("SILICONFLOW_API_KEY 未配置")
        return SiliconFlowClient()
    elif ai_provider == 'openai':
        if not hasattr(settings, 'OPENAI_API_KEY') or not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未配置")
        return OpenAIClient()
    else:
        raise ValueError(f"不支持的AI提供商: {ai_provider}")