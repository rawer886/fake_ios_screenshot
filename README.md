# Android 截图转 iOS 截图工具

将 Android 截图转换为 iOS 设备可以识别的截图格式。

## 功能特性

- ✅ 支持单个文件和批量处理
- ✅ 自动格式转换（JPG/JPEG → PNG）
- ✅ 保持原文件名
- ✅ **保留原始文件的元数据**（EXIF、PNG chunks 等）
- ✅ 保留原始日期时间
- ✅ 输出到单独目录，不修改原文件

## 安装依赖

```bash
# macOS
brew install exiftool

# Linux (Ubuntu/Debian)
apt-get install libimage-exiftool-perl

# Python 依赖
pip3 install Pillow
```

## 使用方法

### 单个文件处理

```bash
python3 convert_to_ios.py screenshot.png
python3 convert_to_ios.py screenshot.jpg output.png
```

### 批量处理目录

```bash
# 输出到输入目录下的 ios_output 子目录
python3 convert_to_ios.py /path/to/images/

# 指定输出目录
python3 convert_to_ios.py /path/to/images/ /path/to/output/
```

**批量处理说明：**
- 自动处理目录下所有图片文件（包括子目录）
- PNG 文件：保持原文件名和扩展名
- JPG/JPEG 文件：输出为同名的 `.png` 文件
- 原文件不会被修改，所有输出保存在指定目录

## 工作原理

脚本会：

1. **格式检测和转换**：自动检测输入格式，JPG/JPEG 转换为 PNG
2. **保留原始元数据**：
   - 从原始文件复制所有 EXIF 数据（使用 exiftool 的 `-tagsFromFile`）
   - 保留所有 PNG chunks（tEXt、iTXt、tIME 等文本元数据）
   - 保留原始文件的修改时间
3. **添加 iOS 截图元数据**：
   - Image Description: "Screenshot"
   - User Comment: "Screenshot"
   - Orientation: Horizontal (normal)
   - Resolution: 144 DPI
   - 这些字段会覆盖已存在的值，但其他元数据会保留
4. **构建正确的 PNG 结构**：
   - 正确的 chunk 顺序：`IHDR → sRGB → [其他chunks] → eXIf → pHYs → sBIT → IDAT → IEND`
   - 添加必要的 PNG chunks（sRGB、eXIf、pHYs、sBIT）
   - 如果原文件已有这些 chunks，会保留原值

## 验证结果

```bash
# 检查 EXIF 元数据
exiftool output.png | grep -E "(Image Description|User Comment|Orientation)"

# 检查 PNG chunk 结构
pngcheck -v output.png
```

## 示例

```bash
# 转换单个文件
python3 convert_to_ios.py android_screenshot.png

# 批量处理当前目录
python3 convert_to_ios.py .

# 批量处理并指定输出目录
python3 convert_to_ios.py ~/Pictures/screenshots/ ~/Pictures/ios_screenshots/
```

## 注意事项

1. **iOS 识别**：转换后的图片需要通过 AirDrop 或文件应用传输到 iOS 设备
2. **输出格式**：输出文件始终是 PNG 格式（iOS 截图要求）
3. **文件名冲突**：如果批量处理时出现同名文件，会自动添加序号

## 文件说明

- `convert_to_ios.py` - 主转换脚本
- `android_screenshot.png` - 示例 Android 截图
- `ios_screenshot_1.PNG`, `ios_screenshot_2.png` - 参考用的 iOS 截图
