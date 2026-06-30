
import pandas as pd
import random


def inject_missing_values(csv_file, output_file, attributes_error_ratio, missing_value_in_ori_data='empty',missing_value_representation='empty'):
    """
    注入空值的错误注入方法，并在注入之前将已有的空值统一替换为指定的表达方式。

    参数:
        csv_file (str): 输入的CSV文件路径。
        output_file (str): 输出的CSV文件路径。
        attributes_error_ratio (dict): 字典，键为属性名，值为错误比例（百分比）。
        missing_value_in_ori_data (str): 原始数据中空值的表达方式（默认值为"empty"）。
        missing_value_representation (str): 空值的表达方式（默认值为"empty"）。

    输出:
        注入错误后的CSV文件。
    """
    # 读取CSV文件
    # dtype=str + keep_default_na=False: read every field as a plain string so
    # that leading-zero postcodes are preserved and no implicit NaN coercion
    # happens before we apply our own missing-value normalisation below.
    df = pd.read_csv(csv_file, dtype=str, keep_default_na=False)
    # 遍历每一列，将可以转换为整数的浮点数转换成整数
    for col in df.columns:
        # 检查列中的数据类型是否为浮点数
        if pd.api.types.is_float_dtype(df[col]):
            # 使用 apply 函数将可以转换成整数的浮点数转换成整数
            df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) and x == int(x) else x)

        # 最后，将列中的所有数据类型都转换为字符串类型
        df[col] = df[col].astype(str)
    # 预处理：将已有的空值（NaN 或 空字符串）替换为 missing_value_representation
    df = df.fillna(missing_value_representation)
    df.replace('', missing_value_representation, inplace=True)
    df.replace('nan', missing_value_representation, inplace=True)
    df.replace('null', missing_value_representation, inplace=True)
    df.replace('__NULL__', missing_value_representation, inplace=True)
    df.replace(missing_value_in_ori_data, missing_value_representation, inplace=True)
    if attributes_error_ratio is None:
        print("没有指定错误比例，仅进行原数据集的空值替换，不添加错误")
    else:
    # 遍历每个属性，注入空值
        for attribute, error_ratio in attributes_error_ratio.items():
            if attribute in df.columns:
                num_rows = len(df)
                num_errors = int(num_rows * error_ratio / 100)
                error_indices = random.sample(range(num_rows), num_errors)

                # 替换指定行的值为空值表达方式
                df.loc[error_indices, attribute] = missing_value_representation

    # 保存注入错误后的CSV文件
    df.to_csv(output_file, index=False)
    print(f"已将注入错误的文件保存到: {output_file}")
if __name__ == "__main__":
    #使用方法
    # 属性列表
    attributes = [
        "journal_issn",
        "journal_title",
        "jounral_abbreviation",
    ]

    # 每个属性注入2%的错误比例
    attributes_error_ratio = {attribute: 0 for attribute in attributes}

    # inject_missing_values(
    #     csv_file='../Data/4_rayyan/dirty_rayyan.csv',
    #     output_file='../Data/4_rayyan/dirty_rayyan.csv',
    #     attributes_error_ratio=attributes_error_ratio,
    #     missing_value_in_ori_data='empty',
    #     missing_value_representation='empty'
    # )
    # 如果干净数据存在空值，记得替换clean数据中的空值，统一转换为empty
    # inject_missing_values(
    #     csv_file='../Data/4_rayyan/dirty.csv',
    #     output_file='../Data/4_rayyan/dirty.csv',
    #     attributes_error_ratio=attributes_error_ratio,
    #     missing_value_in_ori_data='NULL',
    #     missing_value_representation='empty'
    # )
    # 如果干净数据存在空值，记得替换clean数据中的空值，统一转换为empty
    inject_missing_values(
        csv_file='../Data/5_tax/dirty_index_10k.csv',
        output_file='../Data/5_tax/dirty_index_10k.csv',
        attributes_error_ratio=None,
        missing_value_in_ori_data='NaN',
        missing_value_representation='empty'
    )