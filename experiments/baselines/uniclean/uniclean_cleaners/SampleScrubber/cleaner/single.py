import re
import time
from collections import Counter
from datetime import datetime

import numpy as np
from dateparser.date import DateDataParser

from SampleScrubber.cleaner_model import CleanerModel, ParametrizedLanguage, Uniop
from SampleScrubber.util.format import formatString
from collections import Counter
import pandas as pd

"""
    这个类是对单个属性逐行应用的约束。一般在预清洗阶段先执行。
"""


class Single(CleanerModel):
    """
        谓词约束是DataModel的单属性统一形式，作为其他约束的父类不直接使用。
    """

    def __init__(self, domain, check, msg, format, none_penalty=0.01, condition_func=None, ExtDict=None, edit_rule=None,
                 invalidDict=None):
        """构造函数接受一个属性和一个将属性值映射为 true 或 false 的 lambda。

        attr -- 表示谓词所应用的属性的字符串值-
        check -- 一个函数 func(attr) -> {true, false}
        none_penalty -- 对None的惩罚
        """
        self.msg = msg
        self.domain = domain
        self.check = check
        self.format = format
        self.none_penalty = none_penalty
        super(Single, self).__init__(domain=self.domain, source=self.domain, target=self.domain,
                                     msg=self.msg)  # 调用父类的构造函数
        if condition_func is not None:
            # condition_func是一个函数，对source组成对tuple返回 true 或 false
            self.fixValueRules['condition_func'] = condition_func
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

    def _quality(self, df):
        N = df.shape[0]
        qfn_a = np.ones((N,))
        for i in range(N):
            val = df[self.domain].iloc[i]  # 取出第i行的属性值
            if val == None:
                qfn_a[i] = self.none_penalty  # 对None的惩罚
            elif self.check(val):  # 判断单属性下是否满足规则
                qfn_a[i] = 0
        return qfn_a  # 返回一个质量评估的结果

    def preProcess(self):
        raise NotImplementedError("未实现该单列算子的预处理模式")


class Date(Single):
    """Date约束强制datetime字符串字段具有一定的格式。
    """

    def __init__(self, domain, format, name, valid_date_pattern=None, currenFormat=None,condition_func=None, ExtDict=None, edit_rule=None,
                 invalidDict=None):
        """
        Attr——属性名
        Pattern——一个标准的python strftime字符串
        """
        self.name = name
        self.format = format
        self.domain = domain
        self.msg = '[Date:(domain=%s，format = %s)]' % (self.domain, self.format)
        self.valid_date_pattern = valid_date_pattern
        self.currenFormat=currenFormat
        if condition_func is not None:
            # condition_func是一个函数，对source组成对tuple返回 true 或 false
            self.fixValueRules['condition_func'] = condition_func
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

        def timePatternCheck(x, p,v):
            # 检查是否为空或NaN
            if x == None or x != x or len(x.strip()) == 0:
                return False

            try:
                if re.match(valid_date_pattern, x) or not v:
                    # 尝试解析时间字符串，若成功则返回True，否则返回False
                    t = time.strptime(x, p)
                    return True
            except ValueError:
                return False

        super(Date, self).__init__(domain, lambda x, p=format,v=valid_date_pattern: timePatternCheck(x, p,v), self.msg, self.format)

    def __str__(self):
        return self.msg

    from datetime import datetime
    import re
    from dateparser.date import DateDataParser

    def preProcess(self):
        dateInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {
                'domain': ParametrizedLanguage.DOMAIN,
                'format': ParametrizedLanguage.FORMAT,
                'opinformation': ParametrizedLanguage.OPINFORMATION,
            }

            def __init__(self, dateInstance):
                """
                初始化日期时间转换算子。

                参数:
                column: str，待转换的日期时间列名。
                format: str，日期时间格式字符串。
                opinformation: str, 清洗信号名称
                """
                # 读取 dateInstance 中的必要参数
                domain = dateInstance.domain
                format = dateInstance.format
                valid_date_pattern = dateInstance.valid_date_pattern
                currenFormat = dateInstance.currenFormat
                opinformation = str(dateInstance)
                parser = DateDataParser(languages=['en'])

                def fn(df, column=domain, format=format, parser=parser, valid_date_pattern=valid_date_pattern,
                       currenFormat=currenFormat):
                    # 初始化 DataParser
                    if parser is None:
                        parser = DateDataParser(languages=['en'])

                    column_name = column
                    editRuleList = []  # 存储编辑规则

                    # 检查格式是否包含年份且不包含日期
                    contains_year_in_double_obj = format.count('%') == 2 and ("y" in format or "Y" in format)
                    # 如果包含年份，提取分隔符
                    separator = None
                    if contains_year_in_double_obj:
                        separator_match = re.search(r'[^%\w]', re.sub(r'%\w', '', format))
                        separator = separator_match.group(0) if separator_match else None

                    # 定义年份的正则表达式
                    year_pattern = r'^\d{2}$|^\d{4}$'

                    for i in df.index:
                        cell_value = str(df.at[i, column_name])  # 将值转换为字符串

                        # 如果设置了 valid_date_pattern，则首先进行匹配检查
                        if valid_date_pattern and not re.match(valid_date_pattern, cell_value):
                            continue

                        if cell_value:
                            try:
                                # 分隔字符串并检测年份
                                year_str = None
                                #判断两边哪边是年份
                                if separator and contains_year_in_double_obj:
                                    parts = cell_value.split(separator)
                                    left_part, right_part = parts[0], parts[1]
                                    # 检查左右部分是否可能为年份
                                    if re.match(year_pattern, left_part):
                                        year_str = left_part
                                    elif re.match(year_pattern, right_part):
                                        year_str = right_part

                                # 使用指定的当前格式 (currenFormat) 或 DateDataParser 进行解析
                                if currenFormat:
                                    try:
                                        # 首次直接解析
                                        parsed_date = datetime.strptime(cell_value, currenFormat)
                                    except ValueError:
                                        # 若失败，尝试在开头加 0 后重新解析
                                        try:
                                            cell_value_edit = "0" + cell_value
                                            parsed_date = datetime.strptime(cell_value_edit, currenFormat)
                                        except ValueError:
                                            parsed_date = None
                                else:
                                    parsed_data = parser.get_date_data(cell_value)
                                    parsed_date = parsed_data['date_obj']

                                # 如果解析成功且识别到年份
                                if parsed_date and year_str and contains_year_in_double_obj:
                                    # 将两位数年份转换为四位数，假设年份是 2000 年后的
                                    parsed_year = int(year_str) if len(year_str) == 4 else int("20" + year_str)
                                    if parsed_date.year != parsed_year:
                                        parsed_date = parsed_date.replace(year=parsed_year)

                                # 格式化日期为指定的目标格式
                                formatted_date = parsed_date.strftime(format)

                                # 检查是否需要更新值
                                if formatted_date != cell_value:
                                    # 创建修复操作
                                    predicate = ([column_name], {(cell_value,)}, {i})
                                    opinformation = f"Date({column_name},{format})"
                                    editRule = Uniop(
                                        domain=column_name,
                                        repairvalue=formatted_date,
                                        predicate=predicate,
                                        opinformation=opinformation
                                    )
                                    editRuleList.append(editRule)

                                # 更新 DataFrame
                                df.at[i, column_name] = formatted_date
                            except:
                                df.at[i, column_name] = '__NULL__'

                    return df, editRuleList  # 返回更新后的 DataFrame 和编辑规则列表

                # 定义类的名称和溯源信息
                self.name = 'df = dateparse(df,' + formatString(domain) + ',' + formatString(format) + str(
                    opinformation) + ')'
                self.provenance = [self]

                # 调用父类的初始化方法
                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(dateInstance)
class DisguisedMissHandler(Single):
    """DisguisedMissHandler 约束用于处理指定字段的伪装空缺值。
    """

    def __init__(self, domain, format=None, name="MissingValueHandler", missing_values=None):
        """
        domain——需要检查缺失值的属性名
        format——提供的缺省值，如果未提供，将使用列中最常见的值作为缺省值
        missing_values——表示缺失值的字符串列表（如 ["", None, "empty", "null"]）
        """
        self.name = name
        self.format = format
        self.domain = domain
        self.msg = '[MissingValueHandler: (domain=%s, format=%s, missing_values=%s)]' % (
            self.domain, self.format, missing_values)
        self.missing_values = missing_values if missing_values is not None else ["", None, "NaN", "null", "empty"]

        def missCheck(x, missing_values):
            # 检查值是否为空、NaN或包含在缺失值集合中
            if x is None or x != x or x.strip() == "" or x in missing_values:
                return False
            return True
        # 使用 missCheck 进行初始化
        super(DisguisedMissHandler, self).__init__(domain, lambda x, m=missing_values: missCheck(x, m), self.msg,
                                                  format=self.format)

    def __str__(self):
        return self.msg

    def handle_missing(self, df):
        """处理缺失值的函数。"""
        column_name = self.domain
        editRuleList = []  # 存储编辑规则

        # 如果未提供 format，则过滤掉缺失值并计算列中最常见的有效值
        replacement_value = self.format
        if replacement_value is None:
            # 过滤掉空缺值和伪装缺失值
            valid_data = df[column_name][~df[column_name].isin(self.missing_values)].dropna()
            most_common_value = valid_data.mode()

            if not most_common_value.empty:
                replacement_value = most_common_value[0]
            else:
                replacement_value = '__NULL__'  # 如果没有有效值，用默认占位符

        # 遍历列中的每个值并进行替换
        for i in df.index:
            cell_value = df.at[i, column_name]
            # 判断是否为缺失值
            if pd.isna(cell_value) or cell_value in self.missing_values and replacement_value != '__NULL__':
                # 创建替换操作
                predicate = ([column_name], {(cell_value,)}, {i})
                opinformation = f"MissingValueHandler({column_name}, {replacement_value})"
                editRule = Uniop(
                    domain=column_name,
                    repairvalue=replacement_value,
                    predicate=predicate,
                    opinformation=opinformation
                )
                editRuleList.append(editRule)

                # 更新 DataFrame
                df.at[i, column_name] = replacement_value

        return df, editRuleList  # 返回更新的 DataFrame 和编辑规则列表

    def preProcess(self):
        missingValueInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {'domain': ParametrizedLanguage.DOMAIN,
                               'format': ParametrizedLanguage.FORMAT,
                               'opinformation': ParametrizedLanguage.OPINFORMATION,
                               }

            def __init__(self, missingValueInstance):
                """
                初始化缺失值处理算子。

                参数:
                domain: str，待处理缺失值的列名。
                format: str，指定的替换值。如果未提供，将使用列中的最常见值。
                opinformation: str, 清洗信号名称
                """
                domain = missingValueInstance.domain
                format = missingValueInstance.format
                opinformation = str(missingValueInstance)
                missing_values = missingValueInstance.missing_values

                def fn(df, column=domain, format=format, missing_values=missing_values):
                    column_name = column
                    editRuleList = []  # 存储编辑规则

                    # 如果未提供 format，则过滤掉空缺值并计算列中最常见的有效值
                    replacement_value = format
                    if replacement_value is None:
                        # 过滤掉空缺值和伪装缺失值
                        valid_data = df[column_name][~df[column_name].isin(missing_values)].dropna()
                        most_common_value = valid_data.mode()

                        if not most_common_value.empty:
                            replacement_value = most_common_value[0]
                        else:
                            replacement_value = '__NULL__'  # 如果没有有效值，用默认占位符

                    # 遍历列中的每个值并进行替换
                    for i in df.index:
                        cell_value = df.at[i, column_name]
                        # 判断是否为缺失值
                        if pd.isna(cell_value) or cell_value in missing_values:
                            # 创建替换操作
                            predicate = ([column_name], {("__NULL__",)}, {i})
                            opinformation = f"MissingValueHandler({column_name}, {replacement_value})"
                            editRule = Uniop(
                                domain=column_name,
                                repairvalue=replacement_value,
                                predicate=predicate,
                                opinformation=opinformation
                            )
                            editRuleList.append(editRule)

                            # 更新 DataFrame
                            df.at[i, column_name] = replacement_value

                    return df, editRuleList  # 返回更新的 DataFrame 和编辑规则列表

                self.name = 'df = MissingValueHandler(df,' + formatString(domain) + ',' + formatString(format) + str(
                    opinformation) + ')'
                self.provenance = [self]

                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(missingValueInstance)


class Number(Single):
    """约束要求属性必须是限定范围的数值型"""

    def __init__(self, domain, nrange=None, name=None, ExtDict=None, edit_rule=None, invalidDict=None):
        """
        初始化Number类。

        参数:
        domain: str，列名
        nrange: list，允许的数值范围，默认为 [-inf, inf]
        name: str，名称
        """
        if nrange is None:
            nrange = [-np.inf, np.inf]
        self.name = name
        self.attr = domain
        self.format = nrange
        self.msg = '[Number:(domain=%s, format=%s)]' % (self.attr, str(self.format))

        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

        def floatPatternCheck(x):
            # 检查是否为空或是否为浮点数
            if x is None or isinstance(x, float):
                return True
            else:
                return False

        super(Number, self).__init__(domain, lambda x: floatPatternCheck(x), self.msg, self.format)

    def __str__(self):
        return self.msg

    def preProcess(self):
        floatInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {
                'domain': ParametrizedLanguage.DOMAIN,
                'format': ParametrizedLanguage.FORMAT,
                'opinformation': ParametrizedLanguage.OPINFORMATION,
            }

            def __init__(self, floatInstance):
                """
                初始化浮点数转换算子。

                参数:
                domain: str，待转换的列名
                format: list，浮点型的范围
                opinformation: str，清洗信号名称
                """
                domain = floatInstance.attr
                format = floatInstance.format
                opinformation = f"Number({formatString(domain)}, range={format})"

                def fn(df, domain=domain, r=format):
                    editRuleList = []  # 用于存储生成的 Uniop 对象

                    def extract_first_number(value):
                        """提取字符串中的第一个数字，并移除非数字字符。"""
                        # 移除所有字母
                        value_without_letters = re.sub(r'[a-zA-Z]', '', value)
                        # 提取第一个数字
                        match = re.search(r'[-+]?\d*\.?\d+', value_without_letters)
                        return float(match.group(0)) if match else None
                    def __internal(row):
                        try:
                            original_value = row[domain]
                            if isinstance(original_value, str):
                                value = extract_first_number(original_value)
                            else:
                                value = float(original_value)

                            # 检查数值是否在允许范围内
                            if value is not None and r[0] <= value <= r[1]:
                                # 如果不在范围内，创建 Uniop 对象用于修复
                                predicate = ([domain], {(original_value,)}, {row.name})
                                editRule = Uniop(
                                    domain=domain,
                                    repairvalue=value,  # 值不在范围内，设为None
                                    predicate=predicate,
                                    opinformation=opinformation
                                )
                                editRuleList.append(editRule)
                                return value
                            else:
                                return '__NULL__'
                        except:
                            return '__NULL__'

                    # 应用修复操作
                    df[domain] = df.apply(lambda row: __internal(row), axis=1)
                    return df, editRuleList  # 返回 DataFrame 和编辑规则列表

                self.name = 'df = numparse(df,' + formatString(domain) + ',' + str(opinformation) + ')'
                self.provenance = [self]

                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(floatInstance)


class Pattern(Single):
    """Pattern强制字符串字段具有一定的由正则表达式匹配的格式。
    """

    def __init__(self, domain, format, name, condition_func=None, ExtDict=None, edit_rule=None, invalidDict=None):
        """attr——属性名
        pattern——标准的python正则表达式
        """
        self.name = name
        self.format = format
        self.domain = domain
        self.msg = '[Pattern:(domain= %s, format = %s)]' % (self.domain, str(self.format))
        if condition_func is not None:
            # condition_func是一个函数，对source组成对tuple返回 true 或 false
            self.fixValueRules['condition_func'] = condition_func
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

        def patternCheck(x, p):
            # 检查是否为空或NaN，并尝试匹配正则表达式，匹配成功则返回True，否则返回False
            if x is None or x == '' or str(x).strip() == '':
                return False

            try:
                result = re.match(p, x)
                return bool(result)
            except:
                return False

        super(Pattern, self).__init__(domain, lambda x, p=format: patternCheck(x, p), self.msg, self.format)

    def __str__(self):
        # return '属性 %s 是Pattern类型，规则为 %s' % (self.domain, str(self.pattern))
        return self.msg

    def preProcess(self):
        patternInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {'domain': ParametrizedLanguage.DOMAIN,
                               'format': ParametrizedLanguage.FORMAT,
                               'opinformation': ParametrizedLanguage.OPINFORMATION,
                               }

            def __init__(self, patternInstance):
                """
                初始化正则转换算子。

                参数:
                domain: str，待转换的列名。
                format: str，正则模式
                opinformation:str,清洗信号名称
                """
                domain = patternInstance.domain
                format = patternInstance.format
                opinformation = str(patternInstance)

                def extract_first_last_match(pattern):
                    # 找到pattern的第一个匹配部分
                    start_match = re.match(r"^\^?(\[[^\]]+\]|[A-Za-z0-9]+|\([^)]+\))", pattern)
                    first_part = start_match.group(1) if start_match else None

                    # 找到pattern的最后一个匹配部分
                    end_match = re.search(r"(\([^)]+\)|\[[^\]]+\]|[A-Za-z0-9]+)\$?$", pattern)
                    last_part = end_match.group(1) if end_match else None

                    return first_part, last_part

                def trim_to_nearest_match(string, pattern):
                    """
                    Tries to match the pattern directly to the string. If it matches, return the match.
                    If not, iteratively expand from the first and last matched parts of the pattern within the string.
                    """
                    # Attempt a full match first
                    full_match = re.match(pattern, string)
                    if full_match:
                        return full_match.group()  # Return if full match is found

                    # Extract first and last identifiable groups from the pattern
                    first_part, last_part = extract_first_last_match(pattern)

                    # Build a new regex to capture nearest range in the string
                    if first_part and last_part:
                        regex = re.compile(rf"{first_part}.*?{last_part}", re.IGNORECASE)
                        partial_match = regex.search(string)
                        if partial_match:
                            return partial_match.group()  # Return closest match within the bounds of first and last

                    return string  # Return original string if no match found

                def fn(df, domain=domain, format=format):
                    editRuleList = []  # 用于存储生成的 Uniop 对象
                    column_name = domain

                    for i in range(len(df)):
                        cell_value = df.at[i, column_name]
                        if bool(cell_value):
                            try:
                                # 第一步：尝试直接搜索子串
                                match = re.search(format, str(cell_value))
                                if match:
                                    matched_value = match.group(0)
                                else:
                                    # 第二步：使用 trim_to_nearest_match 方法修剪
                                    matched_value = trim_to_nearest_match(str(cell_value), format)

                                # 第三步：如果修剪后的值依然不匹配，则设为 "__NULL__"
                                if not re.match(format, matched_value):
                                    matched_value = "__NULL__"

                                # 更新 DataFrame的操作
                                if matched_value != "__NULL__" and str(cell_value) != matched_value:
                                    # 按照指定格式创建 predicate
                                    predicate = ([column_name], {(cell_value,)}, {i})

                                    # 设置 opinformation 字段
                                    opinformation = f"Pattern({formatString(domain)},{formatString(format)})"

                                    # 创建一个新的 Uniop 对象，并添加到 editRuleList 中
                                    uniop = Uniop(domain=column_name,
                                                  repairvalue=matched_value,
                                                  predicate=predicate,
                                                  opinformation=opinformation)
                                    editRuleList.append(uniop)
                                    self.set_reward(self.reward + 1)

                                # 更新 DataFrame
                                df.at[i, column_name] = matched_value

                            except Exception as e:
                                # 出现异常时，将值设为 "__NULL__"
                                df.at[i, column_name] = "__NULL__"

                    return df, editRuleList  # 返回 DataFrame 和 Uniop 对象列表

                self.name = 'df = pattern(df,' + formatString(domain) + ',' + formatString(format) + str(
                    opinformation) + ')'
                self.provenance = [self]

                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(patternInstance)


class DictValue(Single):
    """
    一个DictValue约束强制一个特定属性的取值范围符合一个字典
    """

    def __init__(self, domain, ExtDict, sim=0.1, condition_func=None, edit_rule=None, invalidDict=None):
        """ DictValue构造函数

        位置参数：
        attr -- 一个属性名称
        codebook -- 一个包含允许域的字典
        """
        self.attr = domain
        self.sim = sim
        self.ExtDict = ExtDict
        super(DictValue, self).__init__(domain, lambda x, ExtDict=self.ExtDict: x in ExtDict)
        if condition_func is not None:
            # condition_func是一个函数，对source组成对tuple返回 true 或 false
            self.fixValueRules['condition_func'] = condition_func
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

    def generateExtDict(df, col, size=100):
        """
        Helper方法按计数选择属性中前k个值
        """

        """计数并返回一个字典，为col中属性值和其数量的键值对（属性值，数量）"""
        s = Counter([v for v in df[col].values if v == str(v)])

        """按数量降序排列，现在l中是（数量，属性值）"""
        l = [i for i in sorted([(s[k], k) for k in s], reverse=True)]
        # print(l)

        """取size大小的切片，里面是属性值"""
        ExtDict = set([occ[1] for occ in l][0:size])

        return ExtDict

    def generateCorrelationExtDict(d, attr, labels, size=100):
        values = set([v for v in d[attr].values if v == str(v)])

        ranked_tokens = []

        for v in values:
            """计算相关系数"""
            corr = np.abs(np.corrcoef(d[attr] == v, labels)[0, 1])
            """添加到ranked_tokens中"""
            ranked_tokens.append((corr, v))
        """降序排序"""
        ranked_tokens.sort(reverse=True)

        return set([v[1] for v in ranked_tokens[:size]])


class Outlier(Single):
    """Outlier约束检测并清理属性中的异常值，包括用户提供的异常集合和内置检测规则。
    """

    def __init__(self, domain, format=None, name="Outlier", condition_func=None, ExtDict=None, edit_rule=None,
                 invalidDict=None):
        """
        Attr——属性名
        format——包含异常值的集合
        """
        self.name = name
        self.domain = domain
        self.format = format or set()
        self.msg = '[Outlier:(domain=%s, outliers= %s)]' % (self.domain, self.format)
        if condition_func is not None:
            self.fixValueRules['condition_func'] = condition_func
        if ExtDict is not None:
            self.fixValueRules['ExtDict'] = ExtDict
        if invalidDict is not None:
            self.fixValueRules['invalidDict'] = invalidDict
        if edit_rule is not None:
            self.fixValueRules['edit_rule'] = edit_rule

        def outlierCheck(x, outliers):
            # 检查值是否为空、NaN或包含在异常值集合中
            if x is None or x != x or x.strip() == "" or any(outlier in x for outlier in outliers):
                return False
            return True

        # 在 super 调用中使用 format 参数
        super(Outlier, self).__init__(domain, lambda x, o=self.format: outlierCheck(x, o), self.msg, format=self.format)

    def __str__(self):
        return self.msg

    def preProcess(self):
        outlierInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {'domain': ParametrizedLanguage.DOMAIN,
                               'format': ParametrizedLanguage.FORMAT,
                               'opinformation': ParametrizedLanguage.OPINFORMATION,
                               }

            def __init__(self, outlierInstance):
                """
                初始化异常值清理算子。

                参数:
                domain: str，待清理的列名。
                format: set，包含异常值的集合。
                opinformation: str，清洗信号名称。
                """
                domain = outlierInstance.domain
                outliers = outlierInstance.format
                opinformation = str(outlierInstance)

                def fn(df, column=domain, outliers=outliers):
                    column_name = column
                    editRuleList = []  # 用于存储生成的 Uniop 对象

                    def remove_outliers(value):
                        # 去除指定的异常字符
                        for outlier in outliers:
                            value = value.replace(outlier, "")
                        # 移除连续的双引号和单引号
                        value = re.sub(r"'{2}", "'", value)  # 将连续的双单引号替换为单个单引号
                        value = re.sub(r'"{2}', '"', value)  # 将连续的双双引号替换为单个双引号
                        # 移除所有非 ASCII 字符
                        value = re.sub(r'[^\x00-\x7F]+', '', value)
                        # 清除多余空格
                        return value.strip()

                    for i in df.index:
                        cell_value = str(df.at[i, column_name]).strip()
                        original_value = cell_value
                        # 去除异常值并处理连续的引号
                        cell_value = remove_outliers(cell_value)

                        # 如果清理后内容有变化，创建修复操作
                        if cell_value != original_value:
                            predicate = ([column_name], {(original_value,)}, {i})
                            opinformation = f"Outlier({formatString(column)}, Outliers={outliers})"
                            editRule = Uniop(
                                domain=column_name,
                                repairvalue=cell_value,
                                predicate=predicate,
                                opinformation=opinformation
                            )
                            editRuleList.append(editRule)
                            df.at[i, column_name] = cell_value  # 更新 DataFrame 的值

                    return df, editRuleList  # 返回 DataFrame 和编辑规则列表

                self.name = 'df = outlier_clean(df,' + formatString(domain) + ',' + str(opinformation) + ')'
                self.provenance = [self]

                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(outlierInstance)
