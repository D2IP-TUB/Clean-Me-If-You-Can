import random

import matplotlib.colors as mcolors
import pandas as pd
import streamlit as st
from PIL import Image

from sysFlowVisualizer.vis_order import *
from AnalyticsCache.get_planuml_graph import *
from SampleScrubber.cleaner.single import *
from SampleScrubber.cleaner.multiple import *

# 这是一个简化版提现清洗结果的页面,用于完全可视化展示
# 设置页面布局
st.set_page_config(layout="wide")
st.subheader('Displaying the workflow of :blue[Cleaning] :coffee:')  # 将子标题修改为英文
# 初始化每个流程的检查
total_clean_check = False
analysis_check = False
sample_check = False
quality_check = False


# 载入数据
def load_Cleaner_data(file_path):
    return pd.read_csv(file_path)


# 处理算子的分类
def display_Cleaners_and_get_list(data):
    # 获取单列算子和多列算子的列表
    single_Cleaners = data[data["Cleaner Category"] == "single"]["Cleaner Type"].tolist()
    multi_Cleaners = data[data["Cleaner Category"] == "multi"]["Cleaner Type"].tolist()
    return single_Cleaners, multi_Cleaners


# 实例化每个我们定义的算子
def instantiate_Cleaners(Cleaners_info, single_Cleaners, multi_Cleaners):
    multi_instantiated_Cleaners = []
    single_instantiated_Cleaners = []
    for op_key, op_info in Cleaners_info.items():
        Cleaner_type = op_info['type']
        Cleaner_name = op_info['name']
        # 实例化多列算子
        if Cleaner_type in multi_Cleaners:
            source_attrs = op_info['source']
            target_attrs = op_info['target']
            for source_attr in source_attrs:
                for target_attr in target_attrs:
                    # 假设 multi 算子的实例化方式是 CleanerType([source], [target])
                    multi_instantiated_Cleaners.append(
                        eval(f"{Cleaner_type}(['{source_attr}'], ['{target_attr}'], '{Cleaner_name}')", globals()))
        # 实例化单列算子
        elif Cleaner_type in single_Cleaners:
            attrs = op_info['attr']
            Cleaner_format = op_info['format']
            for attr in attrs:
                # 假设 single 算子的实例化方式是 CleanerType(attr, format)
                single_instantiated_Cleaners.append(
                    eval(f"{Cleaner_type}('{attr}', '{Cleaner_format}','{Cleaner_name}')", globals()))
    return multi_instantiated_Cleaners, single_instantiated_Cleaners


# 把输入的算子整理成list
def getCleanerInfo(opinfo, single_Cleaners, multi_Cleaners):
    cleaners = []
    for op_key in list(opinfo):
        Cleaner = opinfo[op_key]
        cleaner = {'name': f"{Cleaner['type']}_{op_key}"}

        if Cleaner['type'] in single_Cleaners:
            cleaner_type = 'single'
        elif Cleaner['type'] in multi_Cleaners:
            cleaner_type = 'multi'
        else:
            cleaner_type = 'unknown'
            # 构建 param
        if 'attr' in Cleaner:
            cleaner['attr'] = Cleaner['attr']
            params = "\\n".join([f"attr:{','.join(Cleaner['attr'])}", f"format:{''.join(Cleaner['format'])}"])
        else:
            cleaner['source'] = Cleaner['source']
            cleaner['target'] = Cleaner['target']
            params = "\\n".join(
                [f"source:{','.join(Cleaner['source'])}", f"target:{','.join(Cleaner['target'])}"])

        cleaner['type'] = cleaner_type
        cleaner['param'] = params
        cleaners.append(cleaner)
    return cleaners


# 算子库的内容,并处理分类算子
Cleaners_file = 'TestDataset/cleanersLib.csv'
Cleaners_df = load_Cleaner_data(Cleaners_file)
single_Cleaners, multi_Cleaners = display_Cleaners_and_get_list(Cleaners_df)

all_Cleaners = single_Cleaners + multi_Cleaners  # 合并单列和多列算子列表

# 初始化session state,记录Cleaners用于记录算子
if 'Cleaners' not in st.session_state:
    st.session_state.Cleaners = {}
# 载入一个实例作为演示
df = pd.DataFrame()  # 存储要清洗的数据
columns = []  # 属性列表
Load_Tex_check = st.sidebar.toggle('Load Data Example')
uploaded_file = None
if Load_Tex_check:
    st.sidebar.success("Load Data Completed!")  # 修改为英文
    uploaded_file = 'TestDataset/standardData/tax_200k/dirty_dependencies_0.5/dirty_tax.csv'
    df = pd.read_csv(uploaded_file)
    columns = df.columns.tolist()
    st.session_state.Cleaners = {
        'Cleaner_1': {'type': 'Date', 'attr': ['singleexemp'], 'format': '%I%M%P', 'name': 'Cleaner_1'},
        'Cleaner_2': {'type': 'Pattern', 'attr': ['gender'], 'format': '[M|F]', 'name': 'Cleaner_2'},
        'Cleaner_3': {'type': 'AttrRelation', 'source': ['zip'], 'target': ['city'], 'name': 'Cleaner_3'},
        'Cleaner_4': {'type': 'AttrRelation', 'source': ['zip'],
                      'target': ['state'], 'name': 'Cleaner_4'},
        'Cleaner_5': {'type': 'AttrRelation', 'source': ['areacode'],
                      'target': ['state'], 'name': 'Cleaner_5'},
        'Cleaner_6': {'type': 'AttrRelation', 'source': ['fname', 'lname'],
                      'target': ['gender'], 'name': 'Cleaner_6'}}

# 显示并管理已添加的算子
for op_key in list(st.session_state.Cleaners):
    Cleaner = st.session_state.Cleaners[op_key]
    if Load_Tex_check == True:
        with st.sidebar.expander(f"**{Cleaner['type']} (ID: {op_key})**"):
            # 使用 Markdown 来展示算子的基本信息，以增加视觉效果
            st.markdown(f":blue[**Cleaner Type:**]:**`{Cleaner['type']}`**")
            if Cleaner['type'] in single_Cleaners:
                st.markdown(f":blue[**Attributes:**] **`{Cleaner['attr']}`**")
                st.markdown(f":blue[**Format:**]**`{Cleaner['format']}`**")
            else:
                st.markdown(f":blue[**Source Attributes:**] **`{Cleaner['source']}`**")
                st.markdown(f":blue[**Target Attributes:**]**`{Cleaner['target']}`**")
# st.session_state.Cleaners 包含用户输入的算子及其配置

instantiated_ops = []

with st.container():
    # If a file is uploaded, read its content
    if uploaded_file is not None:
        st.subheader(
            ":white_check_mark: Data uploaded successfully. Proceed with the preliminary analysis of Cleaner parameters.")
    else:
        st.subheader(":heavy_exclamation_mark: Please upload a cleaning task.")

partitions = []
processing_order = []
# 第三列可用于其他内容或留空
if uploaded_file is not None and Load_Tex_check:
    # with st.container():
    #     st.subheader("Cleaner Analysis Module", divider='rainbow')  # 修改为英文
    #     analysis_check = st.toggle('Execute Cleaner Analysis')
    #     # Analysis button
    #     if analysis_check:  # 修改为英文
    #         # Here add the code to execute analysis
    #         # For example, analyze Cleaners in st.session_state.Cleaners and generate topology graphs, etc.
    #         with st.spinner("Analyzing..."):  # 修改为英文
    instantiated_ops = instantiate_Cleaners(st.session_state.Cleaners, single_Cleaners, multi_Cleaners)


    def convert_multi_Cleaners_to_edges(Cleaners):
        edges = []
        for Cleaner_key, Cleaner in Cleaners.items():
            # print(Cleaner_key)
            if Cleaner['type'] in multi_Cleaners:  # Ensure only multi-column Cleaners are processed
                # Create a tuple for each source and target attribute pair and add to edges list
                for source_attr in Cleaner['source']:
                    for target_attr in Cleaner['target']:
                        edges.append(([source_attr], [target_attr]))
        return edges

        # Example: Use this function to convert Cleaner parameters in session_state


    edges = convert_multi_Cleaners_to_edges(st.session_state.Cleaners)
    # print(edges)
    partitions, processing_order, plt = analyze_and_visualize_dependencies(edges)
    explain = explain_analysis_results(partitions, processing_order)
    # Display analysis results
    col1, col2, col3 = st.columns(3)
    with col2:
        st.subheader("Analysis dependencies graph:", divider='rainbow')
        st.pyplot(plt)
        # with col2:
        #     st.subheader("Analysis result:", divider='rainbow')
        #     with st.expander("Partitions", expanded=False):
        #         st.write(partitions)
        #         # print(partitions)
        #
        #     with st.expander("Processing Order", expanded=False):
        #         st.write(processing_order)
        #         # print(processing_order)

    with col3:
        st.subheader("Explanatory:", divider='rainbow')
        st.write(explain)

        # time.sleep(5)  # Simulate the cleaning process  # 修改注释为英文
    with col1:
        st.subheader('Classification of Cleaners from input', divider='rainbow')  # 修改为英文
        # st.subheader('Details of Multi Cleaners', divider='rainbow')  # 修改为英文
        st.markdown(f"""
            ### Details of Rule-based Cleaners:
        """, unsafe_allow_html=True)
        for op in instantiated_ops[0]:
            st.markdown(f"```python\n{str(op)}\n```")
        st.markdown(f"""
            ### Details of Model-based Cleaners:
        """, unsafe_allow_html=True)
        for op in instantiated_ops[1]:
            st.markdown(f"```python\n{str(op)}\n```")
    st.success("Analysis Completed!")  # 修改为英文


# 假设已经通过某种方式获取到了 Partitions 和特定的抽样方法
# def sample_data(df, partitions, sample_ratio):
#     # 在这里实现您的抽样逻辑
#     # 由于示例代码使用了 PySpark，需要将其转换为 Pandas 逻辑
#     # 返回抽样后的 DataFrame
#     sampled_df = df.sample(frac=sample_ratio)  # 简单的随机抽样示例
#     return sampled_df


file_name = './sysFlowVisualizer/cleanCache/'
# 数据采样模块的 Streamlit 代码
if uploaded_file is not None and Load_Tex_check:
    with st.container():
        st.subheader("Data Sampling Module", divider='rainbow')
        # 假设 n 是通过算子分析分离的属性组数量
        n = len(processing_order)  # 或者其他确定 n 的方式

        # 用户选择抽样比例
        sample_ratio = st.slider("Select Sampling Ratio", 0.0, 1.0, 0.3)
        sample_check = st.toggle('Execute Sample Data')

        if sample_check:
            with st.spinner("Sampling..."):
                # sampled_data = sample_data(df, partitions, sample_ratio)
                st.success("Sampling Completed!")

                st.subheader("Sampling Results by Group:")

                for i in range(n):
                    with st.expander(f"Group {i + 1} Sampling Details", expanded=False):
                        # col1 = st.columns(1)
                        # with col1:
                        st.subheader(f'Group {i + 1} Sampled Data:')
                        # 假设每个分组的抽样数据存储在单独的文件中
                        sampled_data_i = pd.read_csv(file_name + f'Sampledata{i}.csv')
                        st.dataframe(sampled_data_i)

                        # with col2:
                        #     st.subheader(f'Group {i + 1} Sampling Distribution Visualization:')
                        #     image = Image.open(file_name + f'resultGraph{i}.png')
                        #     st.image(image, caption=f'Group {i + 1} Sampling Illustration')
                # 保存抽样数据（如果需要）
                # sampled_data.to_csv('path_to_save_sampled_data.csv')

                # 保存抽样数据（如果需要）
                # sampled_data.to_csv('path_to_save_sampled_data.csv')

# 创建模拟的清洗后的数据
# Explanation Texts in English
# 创建模拟的清洗日志


# 检查session_state中的标记
if 'sample_clean_done' not in st.session_state:
    st.session_state.sample_clean_done = False

if uploaded_file is not None and sample_check:
    st.subheader('Interpretable Cleaning Logs:', divider='rainbow')
    quality_check = st.toggle('Cleaning Decision Recommendation')
    # Create columns for each section
    if quality_check:
        col1, col2 = st.columns([1, 1])
        # First Column: Quality Improvement Parameters
        CleanerInfo = getCleanerInfo(st.session_state.Cleaners, single_Cleaners, multi_Cleaners)
        # 更新后的依赖关系，分开定义执行顺序和并行关系
        # 仅选取 multi 类型的 cleaners 进行随机分组
        multi_cleaners = [cleaner for cleaner in CleanerInfo if cleaner['type'] == 'multi']
        # 随机将 multi cleaners 分成三组
        np.random.seed(42)  # 固定随机种子
        random.shuffle(multi_cleaners)  # 打乱顺序以随机分组
        num_groups = 3
        # groups = getGroup(processing_order, CleanerInfo)
        # print(CleanerInfo)
        # groups = [[group] for group in groupsInfo]
        groups = CleanerGouping(CleanerInfo, processing_order)
        # groups = [multi_cleaners[i::num_groups] for i in range(num_groups)]
        # 更新 dependencies 基于排序后的权重
        dependencies = [[cleaner['name'] for cleaner in group] for group in groups]

        # 模拟算子权重用于演示
        group_weights = []
        for group in groups:
            weights = np.random.rand(len(group))
            group_weights.append(list(weights))
        # print(group_weights)
        single_cleaners = [cleaner for cleaner in CleanerInfo if cleaner['type'] == 'single']
        single_weights = np.random.rand(len(single_cleaners))
        # print(single_weights)
        # print(groups)
        # 更新 dependencies 基于排序后的权重
        dependencies = sort_opinfo_by_weights(groups, group_weights)
        # print(processing_order)
        # generate_plantuml_corrected(CleanerInfo)
        # numOP = len(CleanerInfo)
        # # 为每个 Cleaner 附加贡献值（随机权重）
        # weight_op = np.random.rand(numOP)

        # # 创建 DataFrame 展示算子、类型和它们的权重
        # df_cleaners = pd.DataFrame(CleanerInfo)
        # print(df_cleaners)
        # for cleaner in CleanerInfo:
        # df_cleaners['weight'] = group_weights
        # print(df_cleaners)
        # 生成调整后的 PlantUML 文本
        # _, singles, _ = PreParamClassier(cleanners)
        grouped_opinfo = CleanerGouping(CleanerInfo, processing_order)
        single_opinfo = getSingle_opinfo(CleanerInfo, instantiated_ops[1])
        plantuml_text = generate_plantuml_corrected(single_opinfo, grouped_opinfo, dependencies)
        # 添加权重到每个 grouped_opinfo 中
        # print(dependencies)
        PlantUML().process_str(plantuml_text, filename='opPlantuml.svg', directory='sysFlowVisualizer/cleanCache')

        with col1:
            st.subheader('Cleaner Contribute in Cleaning', divider='rainbow')
            # 创建图表
            # 创建颜色列表以区分不同的组
            colors = list(mcolors.TABLEAU_COLORS.values())[:num_groups]

            # 创建一个新的 DataFrame 包含所有 cleaners 和它们的权重
            # # 同时，指定每个 cleaner 所属的组（single cleaners 没有组）
            df_cleaners = pd.DataFrame({
                'name': [cleaner['name'] for cleaner in single_cleaners] + [cleaner['name'] for group in groups for
                                                                            cleaner in group],
                'weight': list(single_weights) + [weight for group_weight in group_weights for weight in group_weight],
                # Correct concatenation

                'group': ['Single' for _ in single_cleaners] + [f'Group {i + 1}' for i, group in enumerate(groups) for _
                                                                in group],
                'param': [cleaner['param'] for cleaner in single_cleaners] + [cleaner['param'] for group in groups for
                                                                              cleaner in group],
            })

            # 可视化，按组绘制 cleaners 的权重
            plt.figure(figsize=(10, 6))
            for label, group_df in df_cleaners.groupby('group'):
                plt.barh(group_df['name'], group_df['weight'], label=(label if label else 'Single'))
            plt.xlabel('Weight')
            plt.ylabel('Cleaner')
            plt.title('Cleaner Weights by Group')
            plt.legend()
            # 在Streamlit应用中展示图表
            st.pyplot(plt)
        with col2:
            st.subheader('Cleaner Order Recommendation', divider='rainbow')
            with open(file_name + 'opPlantuml1.svg', 'r', encoding='utf-8') as file:
                svg_string = file.read()
            st.image(svg_string,
                     caption='opPlantuml',
                     width=300, use_column_width='auto')


if 'total_clean_done' not in st.session_state:
    st.session_state.total_clean_done = False
if uploaded_file is not None and quality_check:
    with st.container():
        st.subheader("ToTal Data Cleaning Module（with Spark）", divider='rainbow')

        # Simulate statistics of the data cleaning process
        accuracy = random.uniform(0.8, 1.0)  # Simulated accuracy  # 修改注释为英文
        recall = random.uniform(0.8, 1.0)  # Simulated recall  # 修改注释为英文
        f1_score = 2 * (accuracy * recall) / (accuracy + recall) if (accuracy + recall) != 0 else 0
        op_num = random.randint(1000, 3000)
        # Simulate the data cleaning process
        total_clean_check = st.toggle('Execute Total Data Cleaning')
        if not st.session_state.total_clean_done:
            if total_clean_check:
                with st.spinner("Cleaning Data..."):
                    time.sleep(2)  # Simulate the time taken for data cleaning  # 修改注释为英文
                st.success("Data Cleaning Completed!")
                # Display statistics
                col1, col2, col3, col4 = st.columns(4)
                st.subheader('Cleaning Performance:', divider='rainbow')
                st.session_state.total_clean_done = True

        else:
            if total_clean_check:
                st.success("Data Cleaning Completed!")
                # Display statistics
        if total_clean_check:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Accuracy", f"{accuracy:.2f}")
            with col2:
                st.metric("Recall", f"{recall:.2f}")
            with col4:
                st.metric("F1 Score", f"{f1_score:.2f}")
            with col3:
                st.metric("Iterations Over Data", f"{op_num}")
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                # st.subheader("Display of Total Repair Data:")
                total_repair = pd.read_csv(file_name + f'total_repair.csv')
                # total_repair = pd.read_csv(file_name + f'sample_repair.csv')
                # 创建模拟DataFrame
                np.random.seed(0)  # 为了可重复性
                random.seed(42)  # Set random seed
                # Cleaner到颜色的映射
                Cleaner_to_color = {
                    'Date_Cleaner_1': '#4169E1',  # 皇家蓝
                    'Pattern_Cleaner_2': '#32CD32',  # 酸橙绿
                    'AttrRelation_Cleaner_3': '#FF8C00',  # 深橙色
                    'AttrRelation_Cleaner_4': '#DB7093',  # 苍白的紫罗兰红色
                    'AttrRelation_Cleaner_5': '#6A5ACD',  # 矢车菊的蓝色
                    'AttrRelation_Cleaner_6': '#20B2AA'  # 浅海洋绿
                }

                # 在 Streamlit 中展示带样式的 DataFrame
                np.random.seed(0)  # 确保可重复性
                # 更新 CleanerInfo 映射，以包含 source 和 target 的信息
                cleaner_to_attributes = {}
                for cleaner in CleanerInfo:
                    sources = cleaner.get('source', [])
                    targets = cleaner.get('target', []) + cleaner.get('attr', [])
                    cleaner_to_attributes[cleaner['name']] = {'sources': sources, 'targets': targets}
                target_to_color = {}
                # print(CleanerInfo)
                for cleaner in CleanerInfo:
                    if 'target' in cleaner:
                        for target in cleaner['target']:
                            target_to_color[target] = Cleaner_to_color[cleaner['name']]
                    if 'attr' in cleaner:
                        for attr in cleaner['attr']:
                            target_to_color[attr] = Cleaner_to_color[cleaner['name']]

                # 重排DataFrame的列，将target_to_color中提到的属性列靠左，其他列排到右边
                columns_ordered = list(target_to_color.keys()) + [col for col in total_repair.columns if
                                                                  col not in target_to_color.keys()]
                total_repair = total_repair[columns_ordered]


                # 定义随机高亮单元格的函数，包括处理source单元格
                def highlight_and_bold(df, num_rows=100):
                    num_rows = min(num_rows, len(df))
                    styles = pd.DataFrame('', index=df.index, columns=df.columns)
                    # 确保每行至少有一个高亮
                    for row in range(num_rows):
                        # 从cleaner_to_attributes随机选择一个cleaner
                        selected_cleaner = np.random.choice(list(cleaner_to_attributes.keys()))
                        color = Cleaner_to_color[selected_cleaner]
                        attrs = cleaner_to_attributes[selected_cleaner]

                        # 随机选择一个target进行高亮，如果该cleaner有多个target
                        if attrs['targets']:
                            selected_target = np.random.choice(attrs['targets'])
                            if selected_target in df.columns:
                                styles.at[row, selected_target] = f'background-color: {color};'

                        # 对所有相关的source应用黑色背景和相同的字体颜色
                        for source in attrs['sources']:
                            if source in df.columns:
                                styles.at[row, source] = f'color: {color}; background-color: #E6E6FA;'
                    return styles


                # 应用随机高亮和加粗到DataFrame的前100行
                styled_df = total_repair.head(100).style.apply(highlight_and_bold, axis=None)
                st.subheader('Total Repair Data Display (Highlight top):')

                # 在 Streamlit 中展示带样式的 DataFrame
                st.dataframe(styled_df)
                # 显示算子名称和对应的颜色标签

            with col2:
                log_file = file_name + 'TotalLog.log'
                st.subheader("Cleaner Color Legend:")
                for op_name, color in Cleaner_to_color.items():
                    st.markdown(
                        f"<span style='display: inline-block; width: 12px; height: 12px; background-color: {color};'></span> {op_name}",
                        unsafe_allow_html=True)
                # # 读取并显示文件的前 10 行
                st.subheader("DownLoad Result")
                # 提供文件下载链接
                st.download_button(label="Download TotalData Log File",
                                   data=open(log_file, "rb"),
                                   file_name="TotalLog.log",
                                   mime="text/plain")

                # 提供文件下载链接
                st.download_button(label="Download total_repair File",
                                   data=open(file_name + 'total_repair.csv', "rb"),
                                   file_name="total_repair.csv",
                                   mime="text/csv")
            with col3:
                st.subheader("Data Repair Examples Showcase")
                st.markdown("""
                #### What's in the table?
                - **Different colors** on the cells represent data repaired by different cleaners.
                - Cells with **colored text** on a light purple background <span style='display: inline-block; width: 12px; height: 12px; margin-right: 5px; background-color: #E6E6FA;'></span> highlight the *source attributes* that influenced the repair, using distinct colors for each cleaner. This color (light purple) is used as a background for source attributes to indicate the influence on the repair process.

                Scroll through to see how data has been intelligently repaired across various rows!
                """, unsafe_allow_html=True)
