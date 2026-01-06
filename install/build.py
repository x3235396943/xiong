"""
用于构建APK的PyInstaller打包脚本
此脚本替代pyproject.toml中的命令定义，提供更灵活的打包选项
"""

import os
import subprocess
import re
from pathlib import Path


def get_latest_version_from_dist(dist_dir):
    """
    从dist目录中找到最新版本号

    Args:
        dist_dir (Path): dist目录路径

    Returns:
        str: 最新版本号，如果没有找到则返回None
    """
    if not dist_dir.exists():
        return None

    # 查找符合模式的文件
    version_pattern = r"pc\.(\d+\.\d+\.\d+(?:\.\d+)*)\.exe"
    max_version = None

    for file_path in dist_dir.iterdir():
        if file_path.is_file():
            match = re.match(version_pattern, file_path.name)
            if match:
                version_str = match.group(1)
                if max_version is None or list(map(int, version_str.split("."))) > list(
                    map(int, max_version.split("."))
                ):
                    max_version = version_str

    return max_version


def increment_version(version_str):
    """
    将版本号的最后一部分加1

    Args:
        version_str (str): 当前版本号，如 "1.2.3"

    Returns:
        str: 递增后的版本号
    """
    version_parts = list(map(int, version_str.split(".")))
    version_parts[-1] += 1
    return ".".join(map(str, version_parts))


def build_apk():
    """执行APK构建过程"""
    # 获取项目根目录
    project_root = Path(os.environ["PIXI_PROJECT_ROOT"])
    assets_dir = project_root / "assets"
    dist_dir = project_root / "dist"

    # 获取最新版本号并递增
    latest_version = get_latest_version_from_dist(dist_dir)
    if latest_version:
        new_version = increment_version(latest_version)
        app_name = f"pc.{new_version}"
        print(f"找到最新版本: {latest_version}, 新版本: {new_version}")
    else:
        # 如果没有找到现有版本，默认从1.0.0开始
        app_name = "pc.1.0.0"
        print("未找到现有版本，使用默认版本: 1.0.0")

    # 构建PyInstaller命令
    cmd = [
        "pyinstaller",
        "--onefile",
    ]

    cmd.extend(["--icon", str(assets_dir / "ICO.ico")])

    # 设置输出名称和入口点
    cmd.extend(["--name", app_name, str(project_root / "install" / "entrypoint.py")])

    print("执行命令:", " ".join(cmd))
    subprocess.run(cmd, cwd=project_root, check=True)
    print("APK构建成功完成!")


if __name__ == "__main__":
    success = build_apk()
