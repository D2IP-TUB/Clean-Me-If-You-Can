import distance
import numpy as np
import pandas as pd

from SampleScrubber.cleaner_model import Uniop
def calculate_similarity_features(source, target):
    """
    计算两个字符串之间的相似性特征。

    参数：
    source (str): 源字符串。
    target (str): 目标字符串。

    返回：
    numpy.ndarray: 包含两个相似性度量的数组。
    """
    source = str(source)
    target = str(target)

    # 计算标准化的 Levenshtein 距离
    normalized_levenshtein_dist = distance.levenshtein(source, target, normalized=True)

    # 分割字符串为单词并转换为小写
    source_tokens = set(source.lower().split())
    target_tokens = set(target.lower().split())

    # 计算集合的交集比例
    token_intersection_ratio = (len(source_tokens.intersection(target_tokens)) + 0.) / (
            len(source_tokens.union(target_tokens)) + 0.)

    similarity_vector = np.zeros((2, 1))
    similarity_vector[0] = normalized_levenshtein_dist
    similarity_vector[1] = token_intersection_ratio

    return similarity_vector


def generate_features(negative_examples, positive_examples, dataframe):
    """
    生成训练数据的特征和标签。

    参数：
    negative_examples (set): 负例的集合。
    positive_examples (set): 正例的集合。
    dataframe (pandas.DataFrame): 数据框架。

    返回：
    SGDClassifier 或 None: 训练好的模型或者无。
    """
    column_names = dataframe.columns.values.tolist()
    num_samples = len(positive_examples) * 2
    num_features = len(column_names) * 2 + 2  # 每列两个特征（domain 和 predicate）
    X = np.zeros((num_samples, num_features))
    Y = np.zeros((num_samples, 1))

    i = 0
    for pos_example in positive_examples:
        if isinstance(pos_example, Uniop):
            feature_vector = np.zeros((num_features, 1))
            domain_index = column_names.index(pos_example.domain)
            predicate_index = column_names.index(pos_example.predicate[0]) + len(column_names)

            feature_vector[domain_index] = 1  # 标记 domain 列
            feature_vector[predicate_index] = 1  # 标记 predicate 列

            if len(pos_example.predicate[1]) != 0:
                similarity_features = calculate_similarity_features(
                    pos_example.repairvalue, next(iter(pos_example.predicate[1])))
                feature_vector[-2:] = similarity_features

            X[i, :] = feature_vector.reshape((-1, num_features))
            Y[i, 0] = 1
            i += 1

    if np.sum(Y) == 0.0:
        return None

    negative_indices = set(np.random.choice(np.arange(len(negative_examples)), int(np.sum(Y))))
    selected_negatives = [list(negative_examples)[j] for j in negative_indices]

    # 处理负例
    for neg_example in selected_negatives:
        if isinstance(neg_example, Uniop):
            feature_vector = np.zeros((num_features, 1))
            domain_index = column_names.index(neg_example.domain)
            predicate_index = column_names.index(neg_example.predicate[0]) + len(column_names)

            feature_vector[domain_index] = 1  # 标记 domain 列
            feature_vector[predicate_index] = 1  # 标记 predicate 列

            if len(neg_example.predicate[1]) != 0:
                similarity_features = calculate_similarity_features(
                    neg_example.repairvalue, next(iter(neg_example.predicate[1])))
                feature_vector[-2:] = similarity_features

            X[i, :] = feature_vector.reshape((-1, num_features))
            i += 1

    valid_indices = np.squeeze(np.argwhere(np.sum(X, axis=1)))
    X_filtered = X[valid_indices, :]
    Y_filtered = Y[valid_indices, 0]

    if len(valid_indices.shape) == 0 or X_filtered.size == 0 or np.sum(X) == 0:
        return None
    # 确保模型至少有一个有效特征
    if np.sum(Y) == 0.0 or np.all((X == 0)):
        return None

    if np.sum(Y) > 0:
        classifier = SGDClassifier(loss='modified_huber', alpha=0.1)
        classifier.fit(X_filtered, Y_filtered)
        return classifier

    return None



def predict_outcome(model, test_feature, dataframe):
    """
    使用模型预测给定的特征是否为正例。

    参数：
    model (SGDClassifier): 训练好的模型。
    test_feature (Uniop): 测试特征。
    dataframe (pandas.DataFrame): 数据框架。

    返回：
    bool: 预测结果。
    """
    column_names = dataframe.columns.values.tolist()
    num_features = len(column_names) * 2 + 2
    X_test = np.zeros((1, num_features))

    if not isinstance(test_feature, Uniop) or len(test_feature.predicate[1]) == 0:
        return True

    domain_index = column_names.index(test_feature.domain)
    predicate_index = column_names.index(test_feature.predicate[0]) + len(column_names)
    X_test[0, domain_index] = 1
    X_test[0, predicate_index] = 1

    similarity_features = calculate_similarity_features(test_feature.repairvalue, next(
        iter(test_feature.predicate[1]))).reshape((2,))
    X_test[0, -2:] = similarity_features

    prediction_probability = np.squeeze(model.predict_proba(X_test))[1]
    return prediction_probability >= 0.25
# 创建一个包含错误的简单数据集
data = {
    'name': ['apple', 'banana', 'chrry', 'date', 'elderberry'],
    'color': ['red', 'yellow', 'red', 'brown', 'purple']
}
df = pd.DataFrame(data)

# 定义一些已知的正确和错误的清洗操作
# 假设我们知道'chrry'是一个拼写错误，应该更正为'cherry'
correct_operations = {
    Uniop('name', 'cherry', ('name', {'chrry'}), 'correct spelling')
}

# 假设错误地更改'banana'为'cherry'是不正确的操作
incorrect_operations = {
    Uniop('name', 'cherry', ('name', {'banana'}), 'incorrect change')
}

# 训练模型
trained_model = generate_features(incorrect_operations, correct_operations, df)

# 验证模型
if trained_model is not None:
    # 定义一些新的测试操作
    test_operations = [
        Uniop('name', 'cherry', ('name', {'chrry'}), 'test correct spelling'),
        Uniop('name', 'cherry', ('name', {'banana'}), 'test incorrect change'),
        Uniop('name', 'apple', ('name', {'aple'}), 'test new operation')
    ]

    for test_op in test_operations:
        prediction = predict_outcome(trained_model, test_op, df)
        print(f"Prediction for operation '{test_op.name}': {'Correct' if prediction else 'Incorrect'}")
else:
    print("Model training failed or returned None.")
