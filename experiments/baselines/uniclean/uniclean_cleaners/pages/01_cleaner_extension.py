import os
import shutil
import time

import pandas as pd
import streamlit as st

st.set_page_config(layout="wide")
st.title("Cleaner Expansion Page")
st.write("This page is for adding new Cleaners to the data cleaning framework.")


def display_Cleaners_and_get_list(df):
    st.subheader("Cleaner classes available for addition to the Cleaner library:", divider='rainbow')
    st.dataframe(df)
    if st.button("Ready to clean?\nReturn to Running Page"):
        st.switch_page("pages/00_framework.py")
    single_Cleaners = df[df["Cleaner Category"] == "single"]["Cleaner Type"].tolist()
    multi_Cleaners = df[df["Cleaner Category"] == "multi"]["Cleaner Type"].tolist()
    return single_Cleaners, multi_Cleaners


def load_Cleaner_data(file_path):
    return pd.read_csv(file_path)


Cleaners_file = 'TestDataset/cleanersLib.csv'
Cleaners_df = load_Cleaner_data(Cleaners_file)
single_Cleaners, multi_Cleaners = display_Cleaners_and_get_list(Cleaners_df)


def render_Cleaner_form(Cleaner_category):
    if Cleaner_category == "single":
        attr_format_file = st.file_uploader("Upload Attribute Format File", type=['py'])
    else:
        qfn_file = st.file_uploader("Upload `qfn` Module File", type=['py'])
    return attr_format_file if Cleaner_category == "single" else qfn_file


def show_code(file_path):
    """展示文件内容的函数"""
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            code = file.read()
            st.code(code)


st.subheader("Cleaner Library Expansion Module:", divider='rainbow')

col1, col2 = st.columns(2)

with col1:
    st.subheader("Cleaner Information Submission Form:", divider='rainbow')
    load_example_check = st.toggle("Load Cleaner Expansion Example")
    example_single_file_path = "sysFlowVisualizer/Float.py"
    example_multi_file_path = "sysFlowVisualizer/function_dependency.py"
    Cleaner_category = st.selectbox("Cleaner Category", ["single", "multi"])
    if load_example_check and Cleaner_category == "single":
        Cleaner_category = "single"  # Assume the example is a single Cleaner
        with st.form("Cleaner_extension_form"):
            Cleaner_category = st.text_input("Cleaner Category", value=Cleaner_category)
            Cleaner_name = st.text_input("Cleaner Name", value="Float")
            Cleaner_description = st.text_area("Cleaner Description",
                                               value="Converts string to float.")
            Cleaner_file = example_single_file_path
            submit_button = st.form_submit_button("Submit Cleaner")
    elif load_example_check and Cleaner_category == "multi":
        Cleaner_category = "multi"
        with st.form("Cleaner_extension_form"):
            Cleaner_category = st.text_input("Cleaner Category", value=Cleaner_category)
            Cleaner_name = st.text_input("Cleaner Name", value="FD")
            Cleaner_description = st.text_area("Cleaner Description",
                                               value="Converts string to float.")
            Cleaner_file = example_multi_file_path
            submit_button = st.form_submit_button("Submit Cleaner")
    else:
        with st.form("Cleaner_extension_form"):
            Cleaner_name = st.text_input("Cleaner Name")
            Cleaner_description = st.text_area("Cleaner Description")
            Cleaner_file = render_Cleaner_form(Cleaner_category)
            submit_button = st.form_submit_button("Submit Cleaner")
if submit_button and Cleaner_name and Cleaner_file:
    file_path = f"./CleanerExtension/{Cleaner_category}/{Cleaner_name}.py"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    if load_example_check:
        # 如果加载了示例，则将示例文件复制到目标位置
        shutil.copyfile(Cleaner_file, file_path)
    else:
        with open(file_path, "wb") as file:
            file.write(Cleaner_file.getvalue())  # Write to file
    time.sleep(1)
    st.success(f"Cleaning Cleaner {Cleaner_name} has been successfully validated and submitted")
    with col2:
        st.subheader("Content of the Uploaded File:", divider='rainbow')
        if (file_path):
            with st.expander("show_code", expanded=False):
                show_code(file_path)
