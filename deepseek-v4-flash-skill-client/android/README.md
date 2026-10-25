# 栖语 Android 测试版

Android 7.0+，arm64 真机及 x86_64 模拟器。WebView 界面、Python 引擎和 SQLite 均在手机应用内运行，不依赖电脑服务。联网推理使用用户自己的 DeepSeek Key；当前消息和所需上下文会发给 DeepSeek，没有另建云端数据库。

## 构建

JDK 17、Gradle 8.9、Android SDK platform 35 / build-tools 34.0.0。Chaquopy 17.1 嵌入 Python 3.11。依赖首次构建需要联网下载。

在本项目目录运行 `android/build-apk.sh`，工具默认位于被 Git 忽略的 `.android-tools/`。也可用 Android Studio 打开 android 目录，配置 SDK 后执行 assembleDebug。

输出：`output/android/qiyu-0.1.1-debug.apk`。这是调试签名测试包，不是应用商店发行包。后续覆盖更新需要保留相同签名；卸载会移除本机数据，先导出备份。

## 使用

把 APK 传到安卓手机，允许所用文件管理器安装未知来源应用。打开栖语，在设置里填入 DeepSeek API Key，保存并测试连接。Key 由 Android Keystore 的 AES-GCM 密钥加密保存，不返回网页，也不进入备份。

电脑已有数据可在网页设置导出 JSON，再传到手机用 App 设置导入。APK 仅内置默认岑野夏模板，不包含开发电脑的人物卡、聊天、数据库或 .env。

## 手机行为与范围

- 内置服务仅绑定手机回环随机端口，全部请求额外校验应用私有凭证。WebView 不导航到外部站点。
- 不请求定位、通讯录、相册或广泛文件权限；导入和导出使用系统文件选择器。
- 禁用系统云备份，私有数据保存在应用目录。
- Android 可能在后台终止进程；本版不提供后台保活、定时主动消息或通知。生成时建议保持前台，回来后可重试失败消息。
- 当前为原型；安装、系统键盘、Key 持久化、备份选择器和真实 API 聊天仍需设备验收。

资源打包由 scripts/bundle_runtime.py 的固定白名单控制。发布前检查 APK 签名及资源中不含私有数据。官方参考：https://chaquo.com/chaquopy/doc/current/android.html
