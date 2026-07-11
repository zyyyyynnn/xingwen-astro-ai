#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/26 12:15
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import copy


def framework_prompt(requirement,background,describe):
    prompt = f"""# Positioning
You are a smart assistant designed to help users select the most suitable framework for executing subsequent tasks based on dataset descriptions and provided a framework option.

# Capabilities
- Analyze dataset characteristics and requirements
- Determine the most appropriate framework based on provided options
- Provide clear framework selection recommendations

# Knowledge Base
- Familiarity with mainstream classification models and sequential models (e.g., Transformer, RNN, LSTM)
- Understanding of fine-tuning methods for multimodal large models
- Proficiency in basic workflows for machine learning tasks

# Dataset Description: 
   - User requirement: {requirement}
   - Data background: {background}
   - Data detail describe: {describe}

# Framework Selection:
   - If the dataset involves image classification tasks and does not require sequential models, recommend using <suggestion>Deep Learning</suggestion>.
   - If the dataset involves traditional machine learning tasks (e.g., classification, regression, clustering), recommend using <suggestion>Machine Learning</suggestion>.
   - If the dataset involves sequential tasks (e.g., time-series forecasting, natural language processing), recommend using <suggestion>SelfModel</suggestion> to build custom sequential models.

# Output Recommendation: Based on the input dataset description, provide the most suitable framework recommendation enclosed in <suggestion></suggestion> tags and briefly explain the reasoning.
"""
#    - If the dataset involves multimodal tasks and requires fine-tuning large models, recommend using <suggestion>Swift</suggestion>.
# "   - If the dataset involves sequential tasks (e.g., time-series forecasting, natural language processing), recommend using <suggestion>SelfModel</suggestion> to build custom sequential models."
    return prompt

def cross_col_recognition_prompt(data_intr,column):
    prompt = f"""# Task
Identify Right Ascension (RA) and Declination (Dec) columns in astronomical data

# Instruction
1. Analyze the provided 'Data description' and 'Column in Data'
2. Determine if any columns represent Right Ascension (RA) and Declination (Dec) coordinates
3. Common RA column names may include: 'ra', 'right_ascension', 'RA', 'R.A.', 'alpha', etc.
4. Common Dec column names may include: 'dec', 'declination', 'DEC', 'Dec.', 'delta', etc.
5. If both RA and Dec columns are found, return a JSON object with the identified column names
6. If either or both are missing, return None

# Provided Information:
- Data description: '''{data_intr["task_describe"]}'''
- Column in Data:  {column}

# Output Example
- Return only valid JSON format or None
- JSON format: {{"ra": "[column_name]", "dec": "[column_name]"}}"""

    return prompt

def task_initial_prompt(goal,background,column,description,framework):
    if framework == "Machine Learning":
        prompt = f"""# Role
You are an expert in the field of astronomy.

# Instruction
Your task is to develop a concise plan for analyzing the dataset based on user goal. Provide:
1. A short summary of the dataset, highlighting its key attributes and relevance to the user’s goal.
2. A list of n exploratory analysis tasks, specifying:
   - Task description: Explain what the task aims to uncover.
   - Task type: Categorize the task (e.g., trend analysis, correlation study, classification, distribution analysis).
   - Selected columns: Specify the relevant data fields, even if transformation is needed.
   - Explanation: Justify why this task is important and how it contributes to the overall analysis.

# Considerations:
- If applicable, recommend visualization techniques (e.g., histograms for distribution, scatter plots for correlation).
- Identify potential challenges in the dataset, such as missing values or outliers.
- Provide insights that are especially useful in astronomical data analysis, such as time-series trends, spatial distributions, and anomaly detection.
- If training a model, ensure proper dataset training, and evaluation within the one exploratory analysis task, rather than handling them as separate recommendations.
- Do not use columns that do not appear in the 'Clean column'.

# User Input
- User goal: {goal}
- Data background: {background}
- Clean column: {column}
- Data description: '''{description}'''

# Output Recommendation
```json
{{
    "summary": "Summarize the dataset, highlighting key characteristics and potential challenges",
    "exploratory_tasks": [
        {{
            "task_description": "Clearly define the objective of this task.",
            "task_type": "Specify whether it's trend analysis, correlation, classification, etc.",
            "selected_columns": [
                {{
                    "column_name": "Specify a relevant column",
                    "column_type": "Specify a relevant column type",
                    "explanation": "Explain why this column is included."
                }},
                {{
                    "column_name": "Specify another relevant column",
                    "column_type": "Specify a relevant column type",
                    "explanation": "Explain its significance."
                }}
            ],
            "explanation": "Provide a clear rationale for why this analysis is valuable."
        }}
    ]
}}```"""
    elif framework == "SelfModel":
        prompt = f"""# Role
You are an expert in data science and astronomy, specializing in feature selection for modeling.

# Instruction
Your task is to analyze the given astronomical dataset and recommend the most suitable fields/features for model training and testing. Provide:
1. A short summary of the dataset, highlighting its key attributes and relevance to the user’s goal.
2. A list of n exploratory recommend training tasks, specifying:
   - Task description: Explain what the task aims to uncover.
   - Task type: Categorize this task (strictly choose only one: classification, prediction, or other). Do not provide any additional content outside these three options.
   - Selected columns: Specify the relevant data fields, even if transformation is needed.
   - Explanation: Justify why this task is important and how it contributes to the overall training task.

# Considerations:
- Do not use columns that do not appear in the 'Clean column'.

# User Input
- User goal: {goal}
- Data background: {background}
- Clean column: {column}
- Data description: '''{description}'''

# Output Recommendation
```json
{{
    "summary": "Summarize the dataset, highlighting key characteristics and potential challenges.",
    "exploratory_tasks": [
        {{
            "task_description": "Clearly define the objective of this task.",
            "task_type": "Specify whether it's classification, prediction or other.(strictly choose only one)",
            "selected_columns": [
                {{
                    "column_name": "Specify a relevant column",
                    "column_type": "Specify a relevant column type",
                    "explanation": "Explain why this column is included."
                }},
                {{
                    "column_name": "Specify another relevant column",
                    "column_type": "Specify a relevant column type",
                    "explanation": "Explain its significance."
                }}
            ],
            "explanation": "Provide a clear rationale for why this training task is valuable."
        }}
    ]
}}```"""
    else:
        print("erro")
    return prompt

def vis_prompt(task,data,summary,explanation,column):
    prompt = f"""# Instruction
According to whether the current task needs to perform a visual analysis, make the following decision:
- If no visual analysis is needed in the task description (e.g., only train the model or perform statistical analysis on the data), return `Over`, and do not return any other values.
- If visual analysis is needed in the task description, proceed to write Python code to analyze the data and solve this task. After finishing the data analysis, use Matplotlib to generate an interactive visualization. Add a suitable legend if different colors are used. Please ensure that only one view is generated. No combination of views is required. If the dataset is large, use stratified sampling by category to ensure representativeness, keeping the total sample size ≤ 1000 for efficient and clear visualization.


# User Input
- Task description: {task}
- Data description: '''{data}'''
- Data summary: {summary}
- Task explanation: {explanation}
- Selected columns: {column}

# Output Example
```python
import matplotlib.pyplot as plt
def execute(data: pd.DataFrame):
    # Data preprocessing
         <codes>

    # plot generation
    plt.figure(figsize=(8, 5))  # (width, height) in inches

    # Customize the plot
    plt.title('Your Plot Title')
    plt.xlabel('X-axis Label')
    plt.ylabel('Y-axis Label')
    plt.tight_layout()  # Adjust layout to prevent clipping

    # Get the figure object to return
    plot_figure = plt.gcf()

    return plot_figure
```"""
    return prompt

def sub_vis_prompt(task,data,column):
    prompt = f"""# Instruction
According to whether the current task needs to perform a visual analysis, make the following decision:
- If no visual analysis is needed in the task description (e.g., only train the model or perform statistical analysis on the data), return `Over`, and do not return any other values.
- If visual analysis is needed in the task description, proceed to write Python code to analyze the data and solve this task. After finishing the data analysis, use Matplotlib to generate an interactive visualization. Add a suitable legend if different colors are used. Please ensure that only one view is generated. No combination of views is required. If the dataset is large, use stratified sampling by category to ensure representativeness, keeping the total sample size ≤ 1000 for efficient and clear visualization.


# User Input
- Task description: {task}
- Data description: '''{data}'''
- Selected columns: {column}

# Output Example
```python
import matplotlib.pyplot as plt
def execute(data: pd.DataFrame):
    # Data preprocessing
         <codes>

    # plot generation
    plt.figure(figsize=(8, 5))  # (width, height) in inches

    # Customize the plot
    plt.title('Your Plot Title')
    plt.xlabel('X-axis Label')
    plt.ylabel('Y-axis Label')
    plt.tight_layout()  # Adjust layout to prevent clipping

    # Get the figure object to return
    plot_figure = plt.gcf()

    return plot_figure
```"""
    return prompt

def data_prompt(task,data,summary,explanation,column):
    prompt = f"""# Instruction
According to whether the current task needs to perform a data analysis, make the following decision:
- If no data analysis is needed in the task description (e.g., only train the model or perform visual analysis on the data.), return `Over`, and do not return any other values.
- If data analysis is needed in the task description, proceed to write Python code to analyze the data and solve this task, focusing on extracting meaningful insights, identifying patterns, and conducting advanced statistical evaluations, rather than using visual analysis methods. This includes, but is not limited to, calculating key metrics, detecting correlations between variables, identifying outliers or anomalies, and performing hypothesis testing or predictive modeling where applicable. The analysis should aim to provide a deep understanding of the data, supported by robust statistical summaries and actionable insights, rather than using simple descriptive statistics. Ensure the code is well-structured, efficient, and includes clear documentation for reproducibility.

# User Input
- Task description: {task}
- Data description: '''{data}'''
- Data summary: {summary}
- Task explanation: {explanation}
- Selected columns: {column}

# Output Example
```python
import pandas as pd

def execute(data: pd.DataFrame):
    # Data preprocessing
    <codes for data preprocessing>

    # Data analysis
    <codes for data analysis>

    # Return results (e.g., summary statistics, insights, or processed data)
    return results
```"""
    return prompt

def sub_data_prompt(task,data,column):
    prompt = f"""# Instruction
According to whether the current task needs to perform a data analysis, make the following decision:
- If no data analysis is needed in the task description (e.g., only train the model or perform visual analysis on the data.), return `Over`, and do not return any other values.
- If data analysis is needed in the task description, proceed to write Python code to analyze the data and solve this task, focusing on extracting meaningful insights, identifying patterns, and conducting advanced statistical evaluations, rather than using visual analysis methods. This includes, but is not limited to, calculating key metrics, detecting correlations between variables, identifying outliers or anomalies, and performing hypothesis testing or predictive modeling where applicable. The analysis should aim to provide a deep understanding of the data, supported by robust statistical summaries and actionable insights, rather than using simple descriptive statistics. Ensure the code is well-structured, efficient, and includes clear documentation for reproducibility.

# User Input
- Task description: {task}
- Data description: '''{data}'''
- Selected columns: {column}

# Output Example
```python
import pandas as pd

def execute(data: pd.DataFrame):
    # Data preprocessing
    <codes for data preprocessing>

    # Data analysis
    <codes for data analysis>

    # Return results (e.g., summary statistics, insights, or processed data)
    return results
```"""
    return prompt

def train_prompt(task,data,summary,explanation,column,fold_path):
    prompt = f"""# Instruction
According to whether the current task needs to train a model, make the following decision: 
- If no training is needed in the task description (e.g., only perform data analysis  or visual analysis on the data.), return `Over`, and do not return any other values.
- If training is needed in the task description, proceed to write Python code to execute:
    1. Train a model: using the provided data.
    2. Analyze the model's performance by evaluating key metrics (e.g., accuracy, precision, recall, F1-score, ROC-AUC).
    3. Store the training parameters.
    4. Visualize the result (e.g., confusion matrix heatmap, ROC curve chart, Test data prediction chart) and save visualized images in directory `{fold_path}\img`.
    5. Ensure the code is well-structured, efficient, and includes clear documentation for reproducibility.

# # User Input
- Task description: {task}
- Data description: '''{data}'''
- Data summary: {summary}
- Task explanation: {explanation}
- Selected columns: {column}

# Output Example
```python
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
from sklearn.ensemble import RandomForestClassifier  # Example model, replace as needed


def execute(data: pd.DataFrame):
    # Data preprocessing
    < codes for data preprocessing >

    # Split data into training and testing sets
    X = data[execute["selected_columns"]]
    y = data['target']  # Replace 'target' with the actual target column name
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # Define the model
    model = RandomForestClassifier(random_state=42)  # Replace with your chosen model

    # Perform n-fold cross-validation
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=kf, scoring='accuracy')

    # Train the model
    model.fit(X_train, y_train)

    # Make predictions
    y_pred = model.predict(X_test)
    y_pred_prob = model.predict_proba(X_test)  # Probabilities for ROC curve calculation

    # Compute performance metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_pred_prob)

    # Store training parameters
    training_params = {{
        'model_type': type(model).__name__,
        'cross_val_mean_accuracy': np.mean(cv_scores),
        'cross_val_std': np.std(cv_scores)
    }}

    # Visualize the result
    < codes for visualization of results >

    # Return results
    results = {{
        'training_params': training_params,
        'performance_metrics': {{
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'roc_auc': roc_auc
        }}
    }}
    return results
```"""
    return prompt

def sub_train_prompt(task,data,column,fold_path):
    prompt = f"""# Instruction
According to whether the current task needs to train a model, make the following decision: 
- If no training is needed in the task description (e.g., only perform data analysis  or visual analysis on the data.), return `Over`, and do not return any other values.
- If training is needed in the task description, proceed to write Python code to execute:
    1. Train a model: using the provided data.
    2. Analyze the model's performance by evaluating key metrics (e.g., accuracy, precision, recall, F1-score, ROC-AUC).
    3. Store the training parameters.
    4. Visualize the result (e.g., confusion matrix heatmap, ROC curve chart, Test data prediction chart) and save visualized images in directory `{fold_path}\img`.
    5. Ensure the code is well-structured, efficient, and includes clear documentation for reproducibility.

# # User Input
- Task description: {task}
- Data description: '''{data}'''
- Selected columns: {column}

# Output Example
```python
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
from sklearn.ensemble import RandomForestClassifier  # Example model, replace as needed


def execute(data: pd.DataFrame):
    # Data preprocessing
    < codes for data preprocessing >

    # Split data into training and testing sets
    X = data[execute["selected_columns"]]
    y = data['target']  # Replace 'target' with the actual target column name
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # Define the model
    model = RandomForestClassifier(random_state=42)  # Replace with your chosen model

    # Perform n-fold cross-validation
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=kf, scoring='accuracy')

    # Train the model
    model.fit(X_train, y_train)

    # Make predictions
    y_pred = model.predict(X_test)
    y_pred_prob = model.predict_proba(X_test)  # Probabilities for ROC curve calculation

    # Compute performance metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_pred_prob)

    # Store training parameters
    training_params = {{
        'model_type': type(model).__name__,
        'cross_val_mean_accuracy': np.mean(cv_scores),
        'cross_val_std': np.std(cv_scores)
    }}

    # Visualize the result
    < codes for visualization of results >

    # Return results
    results = {{
        'training_params': training_params,
        'performance_metrics': {{
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'roc_auc': roc_auc
        }}
    }}
    return results
```"""
    return prompt

def self_model_prompt(task,data,summary,explanation,column, path, type):
    if type == "classification":
        prompt = f"""# Instruction
Your task is to modify the provided code sample based on the user's input. Key areas that may need adjustment include: the data loading section, feature/label selection, and training parameter configuration. Ensure the changes align with the user's specific requirements while do not make any additional modifications.
- Data loading: Update paths, formats, or methods for loading datasets.
- Feature/label selection: Adjust columns, variables, or target specifications.
- Training parameters: Optimize hyperparameters, model settings, or training loops. 

# User Input
- Task description: {task}
- Data description: '''{data}'''
- Data summary: {summary}
- Task explanation: {explanation}
- Selected columns: {column}
- Data path: {path}

# Code Example
```python
make_dir() #Create a directory without making any modifications

# 1. Load dataset, where the first column is the label and the remaining columns are features
data = pd.read_csv("<data path>")
labels = data.iloc[:, 0].values
features = data.iloc[:, 1:].values

# 2. Enable GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 3. Data encoding and vector conversion
X_train, X_test, y_train, y_test, label_encoder = preprocess_data(features, labels) #Do not make any modifications
X_train, X_test, y_train, y_test = convert_to_tensor(X_train, X_test, y_train, y_test) #Do not make any modifications

# 4. Training configuration
batch_size=4096 # Default batch size is 4096, recommended to set to 1024 if using Transformer model
model_type = "LSTM"  # Can be modified to "GRU", "Transformer", or "RNN"
epochs=100
patience=10
warmup_epochs = 5
learning_rate=adjust_learning_rate(batch_size=batch_size) #Do not make any modifications

write_md(text=f"Training Configuration:\\nBatch Size: {{batch_size}}, Model Type: {{model_type}}, Epochs: {{epochs}}, Early Stopping Patience: {{patience}}, Warmup epochs: {{warmup_epochs}}, Learning rate: {{learning_rate}}")  # Log training configuration
model, train_loader, test_loader = select_model_and_loader(model_type, X_train, X_test, y_train, y_test, device,label_encoder, batch_size)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=learning_rate)

# 5. Model training and testing
train_model(model, train_loader, test_loader, criterion, optimizer, device, epochs=epochs, patience=patience, warmup_epochs=warmup_epochs)
test_model(model, test_loader, device, label_encoder)
```"""
    elif type == "prediction":
        prompt = f"""# Instruction
Your task is to modify the provided code sample based on the user's input. Key areas that may need adjustment include: the data loading section, feature/label selection, and training parameter configuration. Ensure the changes align with the user's specific requirements while do not make any additional modifications.
- Data loading: Update paths, formats, or methods for loading datasets.
- Feature/label selection: Adjust columns, variables, or target specifications.
- Training parameters: Optimize hyperparameters, model settings, or training loops. 

# User Input
- Task description: {task}
- Data description: '''{data}'''
- Data summary: {summary}
- Task explanation: {explanation}
- Selected columns: {column}
- Data path: {path}

# Code Example
```python
make_dir() #Create a directory without making any modifications

# 1. Load dataset
data = pd.read_csv("<data path>")
drop_columns = ["Type", "Teff", "logg"]
features = data.drop(columns=drop_columns).values
label_name = ["Teff", "logg", "[Fe/H]"]
labels = data[label_name].values 

# 2. Enable GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 3. Data encoding and vector conversion
X_scaled, Y_scaled, scaler_x, scaler_y = preprocess_data(features, labels) #Do not make any modifications
X_train, X_test, Y_train, Y_test= split_data(X_scaled, Y_scaled) #Do not make any modifications
X_train_tensor, X_test_tensor, Y_train_tensor, Y_test_tensor = prepare_tensors(X_train, X_test, Y_train, Y_test, device)

# 4. Training configuration
batch_size = 4096 # Default batch size is 4096 # Default batch size is 4096
model_type = "LSTM" # Can be modified to "GRU", "Transformer", or "RNN"
epochs=300
patience=30
learning_rate=adjust_learning_rate(batch_size=batch_size) #Do not make any modifications

write_md(text=f"Training Configuration:\\nBatch Size: {{batch_size}}, Model Type: {{model_type}}, Epochs: {{epochs}}, Early Stopping Patience: {{patience}}, Learning rate: {{learning_rate}}") # Log training configuration
train_loader, test_loader = get_data_loaders(X_train_tensor, Y_train_tensor, X_test_tensor, Y_test_tensor, batch_size=batch_size)
model = select_model(model_type=model_type,input_size=X_train.shape[1], hidden_size=128, output_size=Y_train.shape[1],device=device)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=learning_rate)

# 5. Model training and testing
train_model(model, train_loader, test_loader, criterion, optimizer,epochs=epochs,patience=patience)
test_model(model, X_test_tensor, Y_test, scaler_y, lable_name)
```"""
    else:
        print("\033[91m    Error | self model 类型选择出现错误。\033[0m")
    return prompt

def image_cls_model_prompt(requirements,models,data_intr,type):
    models_copy = copy.deepcopy(models)  # 创建完全独立的副本

    for item in models_copy[type]:
        item.pop('Pretrain', None)
        item.pop('Config', None)
        item.pop('Download', None)

    prompt=f"""# Role
You are an AI training configuration assistant. 

# Instruction
Your task is to generate a complete model training configuration based on:
1. The user's input describing their data and goal.
2. The available model information provided.

# Requirements
Strictly follow the numerical order when configuring class labels.

# User Input
- User goal: {requirements}
- Data description: '''{data_intr["task_describe"]}'''

# Available Models
'''{models_copy[type]}'''

# Example Output
```json
{{
  "model": "model_name_from_provided_options",
  "num_classes": 4,
  "classes": ["class1", "class2", "class3", "class4"]
  "explanation": "Clear rationale for the training value."
}}
```"""
    return prompt
