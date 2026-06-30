from SampleScrubber.ModuleTest.SparkClean.spark_rule_model import Uniop as SparkRule



def transformRules(EditRuleList):
    """
    转换编辑规则列表为 Spark 规则列表。

    参数：
    EditRuleList (list): 编辑规则列表。

    返回：
    list: Spark 规则列表。
    """
    SparkRuleList = []
    for EditRule in EditRuleList:
        column = EditRule.domain
        predicate = EditRule.predicate
        value = EditRule.repairvalue
        costfn = EditRule.name
        uniop = SparkRule(column=column,
                          predicate=predicate,
                          value=value,
                          costfn=costfn)
        SparkRuleList.append(uniop)
    return SparkRuleList

def applyRules(rules, data):
    """
    应用规则处理数据。

    参数：
    rules (list): 规则列表。
    data (pandas.DataFrame): 数据框。

    返回：
    pandas.DataFrame: 处理后的数据框。
    """
    for rule in rules:
        data = rule.run(data)
    return data
