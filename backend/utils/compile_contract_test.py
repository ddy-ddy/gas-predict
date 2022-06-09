from backend.utils.utils import get_files_path_dic, process_bar
import dill
import os
import json


# 此函数用于解析solc所返回的合约二进制json集合结果字符串
def analysis_bin_json_result():
    bin_json_str = open("./bin.json", "r")
    try:
        dic = json.load(bin_json_str)["contracts"]
        for contract_path in list(dic.keys()):
            tmp = contract_path.split("/")[-1].split(":")
            if tmp[1] in tmp[0]:
                return list(dic[contract_path].values())[0]
    except:
        return None


# 此函数用于解析solc所返回的合约二进制json集合结果字符串(低版本)
def _analysis_bin_json_result(file_name):
    bin_json_str = open("./bin.json", "r")
    dic = json.load(bin_json_str)["contracts"]
    try:
        for item in dic.items():
            if file_name == item[0].split(":")[-1]:
                return item[1]["bin-runtime"]
        else:
            return None
    except:
        return None


class Complile_helper:
    # 失败的合约地址列表
    fail_contract_list = []

    # 当前处理的合约地址
    now_add = ""
    # 输出字节码的路径
    output_path = "../tmp_files/contracts_bytes/"

    def __init__(self):
        # 修改后的合约存放目录
        ok_contract_files_path = "../tmp_files/ok_contract_files/"
        # 生成一个字典存储文件位置信息
        self.file_path_dic = get_files_path_dic(ok_contract_files_path)
        # 读取编译版本字典
        self.final_version_dic = dill.load(open("../tmp_files/log_pkl/modify_code/final_version.pkl", "rb"))

    def main(self):
        # 遍历每一个修改后的合约
        count = 0
        for items in self.file_path_dic.items():
            contract_name = items[0].split("/")[-1]
            count += 1
            print("{}/{}".format(count, self.file_path_dic.__len__()))
            process_bar(count / self.file_path_dic.__len__())

            folder_path = items[0]
            file_name_list = items[1]
            for file_name in file_name_list:
                # 不编译模板合约代码或构造函数
                if file_name == "model_contract.sol" or file_name == contract_name + ".sol":
                    continue

                self.now_add = folder_path.split("/")[-1]
                funSig = file_name.replace(".sol", "")

                # 完整的合约相对路径
                all_file_path = "{}/{}".format(folder_path, file_name)
                compile_flag = self.compile_contract(all_file_path)

                # 编译合约成字节码以及提取主合约的字节码
                if compile_flag != 0:
                    self.fail_contract_list.append(all_file_path)
                    continue
                else:
                    try:
                        main_contract_bin = _analysis_bin_json_result(contract_name)
                    except:
                        main_contract_bin = analysis_bin_json_result()

                # 把生成的临时的合约字节码json文件删除
                os.remove("./bin.json")

                if main_contract_bin is None:
                    # 如果没有找到主合约的字节码，那么跳过此合约
                    self.fail_contract_list.append(all_file_path)
                    continue
                else:
                    if not os.path.exists(self.output_path + self.now_add):
                        os.makedirs(self.output_path + self.now_add)
                    with open("{}{}/{}.hex".format(self.output_path, self.now_add, funSig), "w", encoding="utf-8") as f:
                        f.write(main_contract_bin)

    def compile_contract(self, all_file_path):
        # 使用solc-select选择版本
        cmd_str = "solc-select use {}".format(self.final_version_dic[self.now_add])
        os.system(cmd_str)

        cmd_str = r"solc {} --combined-json bin-runtime > ./bin.json".format(all_file_path)
        os.system(cmd_str)
        if os.path.exists("./bin.json"):
            with open("./bin.json", "r", encoding="utf-8") as f:
                if f.read() != "":
                    compile_flag = 0
                else:
                    compile_flag = 1
        else:
            compile_flag = 1
        return compile_flag

    def save_log(self):
        dill.dump(self.fail_contract_list, open("../tmp_files/log_pkl/compile_ok_contract/fail_contract_list.pkl", "wb"))


if __name__ == '__main__':
    c = Complile_helper()
    c.main()
    c.save_log()
