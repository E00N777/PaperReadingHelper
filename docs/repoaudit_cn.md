# RepoAudit 源码解读

## dfbscan

该Agent的大概工作流程如下：
```
源值提取 → 过程内分析 → 过程间传播 → 路径收集 → 路径验证 → 生成报告
```

dfbscan的过程内数据流分析逻辑大致如下：
```
def start_scan(self):
    # 对每个源值启动分析
    for src_value in self.src_values:
        worklist = [(src_value, src_function, initial_context)]
        
        while worklist:
            (start_value, start_function, call_context) = worklist.pop(0)
            
            # 构建分析输入
            df_input = IntraDataFlowAnalyzerInput(
                start_function,      # 当前函数
                start_value,         # 起始值（参数/返回值）
                sink_values,         # 汇点集合
                call_statements,     # 函数调用点
                ret_values          # 返回值位置
            )
            
            # 调用LLM进行过程内分析
            df_output = self.intra_dfa.invoke(df_input)
```