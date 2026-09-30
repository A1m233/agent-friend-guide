# 开发验证脚本

需要本机已安装 Python 3.11 或更新版本。入口使用标准库，不安装依赖。

| 名字 | 用途 | mac / Linux | Windows |
| --- | --- | --- | --- |
| check | 运行安装器确定性回归测试 | `./scripts/check/run.sh` | `.\scripts\check\run.ps1` |

默认测试使用模拟网络和临时目录，不安装真实用户模型。已有真实下载 smoke 仅在显式设置 `ARK_MODELS_LIVE_SMOKE=1` 时执行。
