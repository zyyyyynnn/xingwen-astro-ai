import pandas as pd
import altair as alt

def execute(data: pd.DataFrame):
    # Data preprocessing
    # Ensure the necessary columns are present
    required_columns = ['Absolute magnitude(Mv)', 'Radius(R/Ro)', 'Star type']
    if not all(col in data.columns for col in required_columns):
        raise ValueError("DataFrame must contain the following columns: 'Absolute magnitude(Mv)', 'Radius(R/Ro)', 'Star type'")
    
    # Drop rows with missing values in the selected columns
    data = data.dropna(subset=required_columns)
    
    # Convert 'Star type' to categorical for better visualization
    data['Star type'] = data['Star type'].astype('category')
    
    # Chart generation
    brush = alt.selection_interval()  # Brush function for interactive selection
    
    chart = alt.Chart(data).mark_point().encode(
        x='Absolute magnitude(Mv):Q',
        y='Radius(R/Ro):Q',
        color='Star type:N',
        tooltip=['Absolute magnitude(Mv)', 'Radius(R/Ro)', 'Star type']
    ).add_selection(
        brush
    ).properties(
        width=600,
        height=400,
        title='Distribution of Star Types based on Absolute Magnitude and Radius'
    )
    
    return chart

# Example usage:
# Assuming the data is loaded into a DataFrame named `df`
# df = pd.read_csv('stars_data.csv')
# chart = execute(df)
# chart.show()
# df = pd.read_csv(r"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\clean_data\Star dataset to predict star types.csv")
# final_chart=execute(df)
# final_chart.save(r'C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\task_result\202503142158/sub_task0.html', embed_options={'renderer':'svg'})
# final_chart.save(r'C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\task_result\202503142158/sub_task0.png')
