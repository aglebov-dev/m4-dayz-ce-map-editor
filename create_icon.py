#!/usr/bin/env python3
"""
Скрипт для создания стилизованной иконки приложения.
Генерирует иконку с надписью 'm4 dayz' на фоне текущего логотипа.
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

def get_text_dimensions(draw, text, font):
    """
    Получает размеры текста
    """
    # Вместо устаревшего textsize используем bbox
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def create_styled_icon():
    """
    Создает стилизованную иконку с надписью 'm4 dayz'
    """
    # Читаем логотип
    logo_path = "logo.jpg"
    
    if not os.path.exists(logo_path):
        print(f"Error: file {logo_path} not found")
        return None
    
    # Открываем изображение
    img = Image.open(logo_path).convert("RGB")
    
    # Увеличиваем размер для лучшего качества
    base_size = 512
    img = img.resize((base_size, base_size), Image.Resampling.LANCZOS)
    
    # Создаем фон
    bg_color = (30, 30, 40)  # Темно-синий/серый
    bg = Image.new('RGB', (base_size, base_size), bg_color)
    
    # Добавляем логотип как прозрачный слой (снижаем непрозрачность)
    logo_layer = img.copy()
    # Делаем логотип темнее для фона
    enhancer = ImageEnhance.Brightness(logo_layer)
    logo_layer = enhancer.enhance(0.3)
    enhancer = ImageEnhance.Contrast(logo_layer)
    logo_layer = enhancer.enhance(0.5)
    
    # Наложение фона и логотипа
    bg.paste(logo_layer, (0, 0), None)
    
    # Создаем объект для рисования
    draw = ImageDraw.Draw(bg)
    
    # Добавляем текст 'm4 dayz'
    font_path = None
    # Попробуем найти системные шрифты
    possible_fonts = [
        "arial.ttf",
        "arialbd.ttf",
        "segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    
    font_size = 80
    font = None
    
    for fp in possible_fonts:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except:
            continue
    
    if font is None:
        font = ImageFont.load_default()
        print("Using default font")
    
    # Текст: 'm4 dayz'
    text = "m4 dayz"
    
    # Вычисляем позицию текста (центрирование)
    text_width, text_height = get_text_dimensions(draw, text, font)
    text_x = (base_size - text_width) // 2
    text_y = (base_size - text_height) // 2
    
    # Добавляем тень текста
    shadow_offset = 4
    draw.text((text_x + shadow_offset, text_y + shadow_offset), text, font=font, fill=(10, 10, 20))
    
    # Основной текст с градиентом от оранжевого к желтому
    m4_width, _ = get_text_dimensions(draw, "m4", font)
    
    draw.text((text_x, text_y), "m4", font=font, fill=(255, 140, 0))  # Оранжевый
    draw.text((text_x + m4_width, text_y), " dayz", font=font, fill=(200, 200, 100))  # Золотистый
    
    # Добавляем легкий контур
    outline_width = 2
    outline_color = (50, 50, 70)
    draw.text((text_x, text_y), text, font=font, fill=outline_color, stroke_width=outline_width, stroke_fill=outline_color)
    draw.text((text_x, text_y), text, font=font, fill=None, stroke_width=outline_width//2, stroke_fill=(255, 255, 255, 100))
    
    # Сохраняем результат
    result_path = "app_icon.png"
    bg.save(result_path, "PNG")
    print(f"Created icon: {result_path}")
    
    return bg

def convert_to_ico(png_path):
    """
    Конвертирует PNG в ICO с несколькими размерами
    """
    if not os.path.exists(png_path):
        print(f"Error: file {png_path} not found")
        return None
    
    # Создаем ICO с несколькими размерами
    sizes = [16, 32, 48, 64, 128, 256]
    
    # Используем PIL для создания ICO
    img = Image.open(png_path)
    
    # Создаем список изображений разных размеров
    icon_sizes = []
    for size in sizes:
        resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
        icon_sizes.append(resized_img)
    
    # Сохраняем как ICO
    ico_path = "app_icon.ico"
    icon_sizes[0].save(ico_path, format='ICO', sizes=[(s, s) for s in sizes])
    
    print(f"Created ICO icon: {ico_path}")
    return ico_path

def main():
    """Main function"""
    print("Creating styled application icon...")
    
    # 1. Create PNG icon
    icon_image = create_styled_icon()
    if icon_image is None:
        return
    
    # 2. Convert to ICO
    convert_to_ico("app_icon.png")
    
    print("\nIcons created:")
    print("  - app_icon.png (PNG version, 512x512)")
    print("  - app_icon.ico (ICO version with sizes: 16, 32, 48, 64, 128, 256)")

if __name__ == "__main__":
    main()