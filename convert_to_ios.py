#!/usr/bin/env python3
"""
将 Android 截图转换为 iOS 可识别的截图格式

完整的转换流程：
1. 提取原始图像数据
2. 创建基础 PNG（IHDR + sRGB + IDAT + IEND）
3. 使用 exiftool 添加 EXIF 数据（eXIf chunk 会自动插入在 sRGB 之后）
4. 手动插入 pHYs 和 sBIT chunks 到正确位置（eXIf 之后）
5. 保留原始日期

使用方法：
    python3 convert_to_ios.py <图片文件> [输出文件]
    python3 convert_to_ios.py <目录路径> [输出目录]
    
支持格式：PNG、JPG、JPEG 等（会自动转换为 PNG）
"""

import struct
import zlib
import os
import sys
import subprocess
from datetime import datetime
from PIL import Image

def create_png_chunk(chunk_type, data):
    """创建 PNG chunk"""
    crc = zlib.crc32(chunk_type + data) & 0xffffffff
    return (
        struct.pack('>I', len(data)) +
        chunk_type +
        data +
        struct.pack('>I', crc)
    )


def extract_chunks_from_png(filename):
    """从 PNG 文件中提取所有 chunks"""
    with open(filename, 'rb') as f:
        data = f.read()
    
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("不是有效的 PNG 文件")
    
    chunks = []
    i = 8
    while i < len(data) - 12:
        size = struct.unpack('>I', data[i:i+4])[0]
        chunk_type = data[i+4:i+8]
        chunk_data = data[i+8:i+8+size]
        chunks.append((chunk_type, chunk_data))
        i += 12 + size
        if chunk_type == b'IEND':
            break
    
    return chunks


def insert_chunk_after(png_data, insert_after_chunk, new_chunk_type, new_chunk_data):
    """在指定 chunk 之后插入新 chunk"""
    # 查找 insert_after_chunk 的位置
    i = 8  # 跳过 PNG signature
    insert_pos = None
    
    while i < len(png_data) - 12:
        size = struct.unpack('>I', png_data[i:i+4])[0]
        chunk_type = png_data[i+4:i+8]
        chunk_end = i + 12 + size
        
        if chunk_type == insert_after_chunk:
            insert_pos = chunk_end
            break
        
        i = chunk_end
    
    if insert_pos is None:
        # 如果找不到，在 IEND 之前插入
        insert_pos = len(png_data) - 12
    
    # 插入新 chunk
    new_chunk = create_png_chunk(new_chunk_type, new_chunk_data)
    return png_data[:insert_pos] + new_chunk + png_data[insert_pos:]


def convert_android_to_ios(input_path, output_path=None, preserve_date=True):
    """
    将 Android 截图转换为 iOS 可识别的截图格式
    支持 PNG、JPG、JPEG 等格式
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_ios.png"  # 输出总是 PNG 格式
    
    # 保存原始文件路径（用于获取日期）
    original_input_path = input_path
    
    # 读取原始图片以获取日期和格式信息
    img = Image.open(input_path)
    
    # 检查文件格式，如果不是 PNG，先转换为 PNG
    is_png = False
    temp_png = None
    try:
        with open(input_path, 'rb') as f:
            header = f.read(8)
            is_png = header[:8] == b'\x89PNG\r\n\x1a\n'
    except:
        pass
    
    # 如果不是 PNG，先转换为 PNG
    if not is_png:
        if not hasattr(convert_android_to_ios, '_batch_mode'):
            print(f"检测到非 PNG 格式，正在转换为 PNG...")
        temp_png = output_path + '.temp_png'
        # 转换为 RGB 模式（JPG 可能是其他模式）
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(temp_png, 'PNG')
        input_path = temp_png
        if not hasattr(convert_android_to_ios, '_batch_mode'):
            print(f"✅ 已转换为 PNG: {temp_png}")
    
    # 获取原始日期（从原始文件获取，不是临时文件）
    datetime_original = None
    if preserve_date:
        # 先尝试从原始图片的 EXIF 获取
        try:
            original_img = Image.open(original_input_path)
            exif = original_img.getexif()
            if exif:
                from PIL.ExifTags import TAGS
                for tag_id, value in exif.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == 'DateTimeOriginal':
                        datetime_original = str(value)
                        break
        except:
            pass
        
        # 如果 EXIF 中没有，从原始文件的修改时间获取
        if datetime_original is None:
            try:
                mtime = os.path.getmtime(original_input_path)
                dt = datetime.fromtimestamp(mtime)
                datetime_original = dt.strftime("%Y:%m:%d %H:%M:%S")
            except:
                datetime_original = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
    else:
        datetime_original = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
    
    if not hasattr(convert_android_to_ios, '_batch_mode'):
        print(f"原始日期: {datetime_original}")
    
    # 提取原始 PNG chunks
    chunks = extract_chunks_from_png(input_path)
    
    # 分类 chunks：需要保留的和需要处理的
    ihdr_chunk = None
    srgb_chunk = None
    idat_chunks = []
    other_chunks = []  # 保留其他所有 chunks（tEXt、iTXt、tIME 等）
    
    for chunk_type, chunk_data in chunks:
        if chunk_type == b'IHDR':
            ihdr_chunk = (chunk_type, chunk_data)
        elif chunk_type == b'sRGB':
            srgb_chunk = (chunk_type, chunk_data)
        elif chunk_type == b'IDAT':
            idat_chunks.append((chunk_type, chunk_data))
        elif chunk_type not in [b'IEND', b'eXIf', b'pHYs', b'sBIT']:
            # 保留所有其他 chunks（tEXt、iTXt、tIME、tRNS 等），但排除我们要处理的
            other_chunks.append((chunk_type, chunk_data))
    
    # 步骤 1: 创建基础 PNG（IHDR + sRGB + 其他chunks + IDAT + IEND）
    png_data = b'\x89PNG\r\n\x1a\n'
    
    # IHDR
    if ihdr_chunk:
        png_data += create_png_chunk(*ihdr_chunk)
    
    # sRGB
    if srgb_chunk:
        png_data += create_png_chunk(*srgb_chunk)
    else:
        png_data += create_png_chunk(b'sRGB', b'\x00')
    
    # 保留其他 chunks（在 sRGB 之后，IDAT 之前）
    for chunk_type, chunk_data in other_chunks:
        png_data += create_png_chunk(chunk_type, chunk_data)
    
    # IDAT chunks
    for chunk_type, chunk_data in idat_chunks:
        png_data += create_png_chunk(chunk_type, chunk_data)
    
    # IEND
    png_data += create_png_chunk(b'IEND', b'')
    
    # 步骤 2: 写入临时文件，使用 exiftool 添加 EXIF
    temp_file1 = output_path + '.temp1'
    with open(temp_file1, 'wb') as f:
        f.write(png_data)
    
    # 使用 exiftool 添加/更新 EXIF 数据，同时保留原有元数据
    try:
        cmd = ['exiftool', '-overwrite_original']
        
        # 从原始文件复制所有 EXIF 数据（无论是 PNG 还是 JPG）
        if os.path.exists(original_input_path):
            # 从原始文件复制所有标签，但允许我们覆盖特定字段
            cmd.extend([
                '-tagsFromFile', original_input_path,
                '-all:all',  # 复制所有标签
                '-unsafe',   # 允许复制不安全标签
            ])
        
        # 添加/更新 iOS 截图必需的元数据（会覆盖已存在的值）
        cmd.extend([
            '-ImageDescription=Screenshot',
            '-UserComment=Screenshot',
            f'-DateTimeOriginal={datetime_original}',
            f'-ModifyDate={datetime_original}',
            f'-CreateDate={datetime_original}',
            '-Orientation=1',  # Horizontal (normal)
            '-XResolution=144',
            '-YResolution=144',
            '-ResolutionUnit=2',  # inches
            '-ColorSpace=1',  # sRGB
            temp_file1
        ])
        
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if not hasattr(convert_android_to_ios, '_batch_mode'):
            print("✅ exiftool 执行成功")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  exiftool 执行失败: {e.stderr}")
        if os.path.exists(temp_file1):
            os.remove(temp_file1)
        return None
    except FileNotFoundError:
        print("⚠️  错误: exiftool 未安装")
        print("   请安装 exiftool: brew install exiftool (macOS)")
        if os.path.exists(temp_file1):
            os.remove(temp_file1)
        return None
    
    # 步骤 3: 读取 exiftool 处理后的文件，插入 pHYs 和 sBIT chunks
    with open(temp_file1, 'rb') as f:
        png_data = f.read()
    
    # 检查是否已有 pHYs chunk（如果有，保留原值；如果没有，添加）
    has_phys = False
    temp_chunks = extract_chunks_from_png(temp_file1)
    for chunk_type, _ in temp_chunks:
        if chunk_type == b'pHYs':
            has_phys = True
            break
    
    # 在 eXIf chunk 之后插入 pHYs（如果不存在）
    if not has_phys:
        phys_data = struct.pack('>IIB', 5669, 5669, 1)  # 144 DPI
        png_data = insert_chunk_after(png_data, b'eXIf', b'pHYs', phys_data)
    
    # 检查是否已有 sBIT chunk（如果有，保留原值；如果没有，添加）
    has_sbit = False
    for chunk_type, _ in temp_chunks:
        if chunk_type == b'sBIT':
            has_sbit = True
            break
    
    # 在 pHYs chunk 之后插入 sBIT（如果不存在）
    if not has_sbit:
        sbit_data = struct.pack('BBB', 8, 8, 8)
        png_data = insert_chunk_after(png_data, b'pHYs', b'sBIT', sbit_data)
    
    # 写入最终文件
    with open(output_path, 'wb') as f:
        f.write(png_data)
    
    # 清理临时文件
    if os.path.exists(temp_file1):
        os.remove(temp_file1)
    
    # 清理转换后的临时 PNG 文件（如果存在）
    if temp_png and os.path.exists(temp_png):
        os.remove(temp_png)
    
    # 保留原始文件的修改时间（使用原始文件，不是临时文件）
    if preserve_date:
        try:
            mtime = os.path.getmtime(original_input_path)
            os.utime(output_path, (mtime, mtime))
        except:
            pass
    
    # 修复 Orientation（exiftool 有时会设置错误的值）
    try:
        subprocess.run(['exiftool', '-Orientation=1', '-n', '-overwrite_original', output_path], 
                      capture_output=True, text=True, check=True)
    except:
        pass
    
    # 验证结果（仅在单文件模式下显示详细信息）
    if not hasattr(convert_android_to_ios, '_batch_mode'):
        try:
            result = subprocess.run(['exiftool', '-s3', '-ImageDescription', output_path], 
                                  capture_output=True, text=True, check=True)
            if result.stdout.strip() == 'Screenshot':
                print(f"✅ 转换完成: {output_path}")
                print("   ✅ Image Description: Screenshot")
            else:
                print(f"⚠️  警告: Image Description 可能不正确")
        except:
            pass
    
    # 验证 chunk 顺序（仅在单文件模式下显示详细信息）
    if not hasattr(convert_android_to_ios, '_batch_mode'):
        try:
            result = subprocess.run(['pngcheck', '-v', output_path], 
                                  capture_output=True, text=True, check=True)
            lines = result.stdout.split('\n')
            chunk_order = [line for line in lines if 'chunk' in line.lower()][:6]
            print("\nChunk 顺序:")
            for line in chunk_order:
                print(f"   {line.strip()}")
        except:
            pass
    
    return output_path


def get_image_files(directory):
    """获取目录下所有图片文件"""
    image_extensions = {'.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG'}
    image_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            _, ext = os.path.splitext(file)
            if ext in image_extensions:
                image_files.append(os.path.join(root, file))
    
    return sorted(image_files)


def process_directory(directory, output_dir=None, preserve_date=True):
    """批量处理目录下的所有图片"""
    if not os.path.isdir(directory):
        print(f"错误: {directory} 不是一个有效的目录")
        return
    
    image_files = get_image_files(directory)
    
    if not image_files:
        print(f"在目录 {directory} 中未找到图片文件")
        return
    
    # 如果没有指定输出目录，使用输入目录下的 ios_output 子目录
    if output_dir is None:
        output_dir = os.path.join(directory, 'ios_output')
    
    # 创建输出目录（如果不存在）
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}\n")
    
    print(f"找到 {len(image_files)} 个图片文件，开始处理...\n")
    
    # 设置批量模式标志（减少详细输出）
    convert_android_to_ios._batch_mode = True
    
    success_count = 0
    fail_count = 0
    
    # 用于跟踪已使用的文件名，避免重复
    used_filenames = {}
    
    for i, image_file in enumerate(image_files, 1):
        print(f"[{i}/{len(image_files)}] 处理: {os.path.basename(image_file)}")
        
        # 确定输出文件名：保持原文件名，但如果是非PNG格式，输出为PNG
        base_name = os.path.basename(image_file)
        base, ext = os.path.splitext(base_name)
        
        if ext.lower() in ['.jpg', '.jpeg']:
            # JPG 输入，输出为 PNG（保持原文件名）
            output_filename = base + '.png'
        else:
            # PNG 输入，保持原文件名和扩展名
            output_filename = base_name
        
        # 处理重复文件名：如果文件名已存在，添加序号
        if output_filename in used_filenames:
            used_filenames[output_filename] += 1
            base_name_part, ext_part = os.path.splitext(output_filename)
            output_filename = f"{base_name_part}_{used_filenames[output_filename]}{ext_part}"
        else:
            used_filenames[output_filename] = 0
        
        # 输出文件路径
        output_file = os.path.join(output_dir, output_filename)
        
        try:
            result = convert_android_to_ios(image_file, output_file, preserve_date)
            if result:
                success_count += 1
                print(f"   ✅ 完成 -> {output_filename}\n")
            else:
                fail_count += 1
                print(f"   ❌ 失败\n")
        except Exception as e:
            fail_count += 1
            print(f"   ❌ 错误: {e}\n")
    
    # 清除批量模式标志
    if hasattr(convert_android_to_ios, '_batch_mode'):
        delattr(convert_android_to_ios, '_batch_mode')
    
    print("=" * 50)
    print(f"处理完成！成功: {success_count}, 失败: {fail_count}")
    print(f"输出目录: {output_dir}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  单个文件: python3 convert_to_ios.py <图片文件> [输出文件]")
        print("  批量处理: python3 convert_to_ios.py <目录路径> [输出目录]")
        print("\n示例:")
        print("  python3 convert_to_ios.py screenshot.png")
        print("  python3 convert_to_ios.py /path/to/images/")
        print("  python3 convert_to_ios.py /path/to/images/ /path/to/output/")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 检查是文件还是目录
    if os.path.isdir(input_path):
        # 批量处理目录
        process_directory(input_path, output_path)
    elif os.path.isfile(input_path):
        # 处理单个文件
        result = convert_android_to_ios(input_path, output_path)
        if result:
            print("\n提示: 如果 iOS 设备仍然无法识别，请尝试：")
            print("  1. 确保图片通过 AirDrop 或文件应用传输到 iOS 设备")
            print("  2. 在 iOS 照片应用中查看图片信息，确认显示为 'Screenshot'")
    else:
        print(f"错误: {input_path} 不存在或不是有效的文件/目录")
        sys.exit(1)

