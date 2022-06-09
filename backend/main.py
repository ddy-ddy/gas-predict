import os

from backend.utils import modify_code_for_test, compile_contract_test, PYG_data
from backend.utils import test_model
from backend.utils.Explainer.explain_main import Explainer

# 将工作路径设定到utils里，否则相对路径将错误
os.chdir("./utils")

# 第一步修改合约函数的源代码，为主合约的每个函数生成一个合约
modify_code_tool = modify_code_for_test.FunctionCodeBuilder()
modify_code_tool.main()

# 第二步编译合约
compiler = compile_contract_test.Complile_helper()
compiler.main()

# 第三步利用合约编译后的字节码生成OPCFG并构建成dgl_data,所有dgl信息放在cfg_build里的pkl文件
# 注意，此处不需要调用代码，直接引用，因为引用的py文件里没有main函数，会直接执行（不能加main函数，因为用了多进程）
from backend.utils import build_cfg_and_dataset  # 这行不能删

# 第四步把dgl数据转换成PYG框架的数据
dataset = PYG_data.GasPredictorDataset(name="500-1")

# 第五步读取模型并投入数据测试
test_model = test_model.Test_model(dataset)
addFunSig_list, pre_list = test_model.main()
pre_list = [list(item.detach().numpy()) for item in pre_list]

# 保存数据
info = []
for i, item in enumerate(addFunSig_list):
    info.append([item.split(":")[1], pre_list[i]])
import pandas as pd

data = pd.DataFrame({"name": [item[0] for item in info], "data": [item[1] for item in info]})
data.to_csv("data.csv", index=False)

# # 第六步解释预测结果并输出cfg图
# explainer = Explainer(dataset=dataset, addFunSig_list=addFunSig_list, pre_list=pre_list,
#                       model=test_model.model, device=test_model.args.device)
# explainer.main()
