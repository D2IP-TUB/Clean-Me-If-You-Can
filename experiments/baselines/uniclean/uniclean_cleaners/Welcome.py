#这个是一键端的可视化页面，启动命令为：
# streamlit run Welcome.py
import streamlit as st

def run():
    st.set_page_config(page_title="UniClean", page_icon="🧹", layout="wide")

    # Sidebar navigation
    page = st.sidebar.radio("Choose Functionality to Introduce",
                            ["Overview", "Analysis of Cleaner Params", "Cleaning Parameter Pipeline",
                             "Analyzing Cleaner Contributions & Visualizing Execution Flow"])

    # Page Header
    st.title("UniClean Data Cleaning System")
    st.subheader("Welcome to UniClean 👋")

    # Introduction to UniClean
    st.markdown("""
    ### Welcome to UniClean, an advanced data cleaning framework designed to address the complexity and diversity in data cleaning processes.

    In the realm of data-intensive tasks, the quality of data is paramount. Yet, real-world data often comes with its flaws, encountering issues stemming from its diversity and the complexities of its applications. Traditional frameworks fall short, being too rigid to adapt to these challenges without extensive pre-existing data labels.
    ### Explore UniClean
    Dive into the system demonstration to witness UniClean in action and understand its operation firsthand.
    """)
    if st.button("Go to UniClean Running Page"):
        st.switch_page("pages/00_framework.py")
    file_path = "./sysFlowVisualizer/pic5.svg"
    with open(file_path, 'r', encoding='utf-8') as file:
        svg_string = file.read()
    st.image(svg_string, caption='Figure 1: UniClean Framework', use_column_width=True)
    st.markdown("""
        ### Why UniClean?
        - **Unified Data Cleaning Pipeline:** Leveraging the Uniop meta-language, UniClean merges disparate cleaning methods into a singular framework. This fosters collaboration and increases both flexibility and efficiency.
        - **Goal-oriented Strategy Optimization:** With techniques like representative sample mining and dynamic parameter adjustment, UniClean tailors its approach to cleaning objectives, adeptly navigating through various data quality challenges.
        - **Interpretable Decision Recommendations:** Providing insights at the macro level, UniClean assists business professionals in grasping the nuances of data processing, thereby streamlining decision-making and elevating the quality of data handling.
        """)
    # Depending on the page selected, show different content
    if page == "Overview":
        st.header("System Overview")
        # Assuming the image is an SVG for high-quality display
        st.markdown("""
            The UniClean system is crafted to refine data set quality through specific cleaning targets, optimizing with precision and documenting the process for informed decision-making. It's built to adapt to the varied environments of large data sets, aiding business professionals in their decisions and comprehension.

            The architecture comprises two cleaning pipelines and models: the Cleaning Parameter Generation Pipeline (J), the Cleaning Parameter Selection Pipeline (K), the dynamic Quality Model (Q), and the Cleaning Decision Recommendation Model (M). This structure spans the entire process from adaptive strategy deployment to interpretive decision-making guidance.
            """)
    elif page == "Analysis of Cleaner Params":
        st.header("Analysis of Cleaner Params")
        st.markdown(
            "This section demonstrates how UniClean optimizes Analysis of Cleaner Params processes for effective cleaning.")

    elif page == "Cleaning Parameter Pipeline":
        st.header("Cleaning Parameter Pipeline")
        st.markdown("Explore the dynamic adjustment of cleaning parameters within UniClean to enhance data quality.")

    elif page == "Analyzing Cleaner Contributions & Visualizing Execution Flow":
        st.header("Analyzing Cleaner Contributions & Visualizing Execution Flow")
        st.markdown(
            "Learn how UniClean evaluates the quality of cleaned data, ensuring the highest standards are upheld.")


if __name__ == "__main__":
    run()
