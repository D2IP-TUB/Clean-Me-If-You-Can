from dateparser.date import DateDataParser
import re

# 初始化 DateDataParser
parser = DateDataParser(languages=['en'])

# 日期字符串和格式
date_str = "Jan-2015"  # 您可以使用 "15-Jan", "Jan-15", 或 "2015-Jan" 等不同格式进行测试
date_format = "%y-%b"

# 提取分隔符，确保排除 %
separator_match = re.search(r'[^%\w]', date_format)
separator = separator_match.group(0) if separator_match else None

if separator:
    # 使用分隔符分割日期字符串
    parts = date_str.split(separator)
    left_part = parts[0]
    right_part = parts[1]

    # 定义正则表达式来识别年份（两位或四位数字）
    year_pattern = r'^\d{2}$|^\d{4}$'

    # 判断左右哪一部分可能是年份
    year_str = None
    if re.match(year_pattern, left_part):  # 左侧是两位或四位数字
        year_str = left_part
    elif re.match(year_pattern, right_part):  # 右侧是两位或四位数字
        year_str = right_part

    # 使用 DateDataParser 解析日期
    parsed_date = parser.get_date_data(date_str)['date_obj']

    # 如果解析成功
    if parsed_date and year_str:
        # 将两位数年份转换为四位数，假设年份是2000年后的
        parsed_year = int(year_str) if len(year_str) == 4 else int("20" + year_str)

        # 检查解析结果的年份是否与识别出的年份一致
        if parsed_date.year != parsed_year:
            parsed_date = parsed_date.replace(year=parsed_year)  # 替换为识别出的年份

        # 格式化日期
        formatted_date = parsed_date.strftime("%y-%b")
        print("Original:", date_str)
        print("Formatted:", formatted_date)
    else:
        print("无法解析日期字符串或识别年份。")
else:
    print("无法提取到分隔符。")