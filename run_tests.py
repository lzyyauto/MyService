#!/usr/bin/env python
"""
视频处理功能测试运行器
运行所有相关测试并生成报告
"""

import sys
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0


def main():
    """主函数"""
    print("\n🚀 视频处理功能测试套件")
    print("="*60)

    # 测试文件列表
    test_files = [
        ("tests/test_ai_client.py", "AI客户端单元测试"),
        ("tests/test_video_processor_service.py", "视频处理服务单元测试"),
        ("tests/integration/test_video_process_api.py", "API集成测试"),
    ]

    all_passed = True

    # 运行单元测试
    print("\n📦 单元测试")
    print("-"*60)
    for test_file, description in test_files:
        if Path(test_file).exists():
            success = run_command(
                f"pytest {test_file} -v",
                f"{description} - {test_file}"
            )
            if not success:
                all_passed = False
                print(f"❌ {description} 失败")
        else:
            print(f"⚠️  测试文件不存在: {test_file}")

    # 运行所有测试
    if all_passed:
        print("\n\n🔄 运行所有测试")
        print("-"*60)
        success = run_command(
            "pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html",
            "完整测试套件（含覆盖率）"
        )
        if not success:
            all_passed = False
            print("❌ 完整测试套件 失败")

    # 运行特定测试（如果指定）
    if len(sys.argv) > 1:
        test_pattern = sys.argv[1]
        print(f"\n\n🎯 运行匹配测试: {test_pattern}")
        print("-"*60)
        success = run_command(
            f"pytest tests/ -k '{test_pattern}' -v",
            f"匹配测试: {test_pattern}"
        )
        if not success:
            all_passed = False

    # 总结
    print("\n" + "="*60)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败")
    print("="*60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
