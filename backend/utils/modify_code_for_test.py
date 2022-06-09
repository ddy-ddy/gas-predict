from slither.slither import Slither, SlitherError
import dill as pickle
import os
import linecache
from backend.utils.utils import get_files_path, process_bar, \
    add_internal_for_functions, get_lines_by_pos
import shutil

# 目前支持的合约版本
solidity_version_support_list = ['0.4.10', '0.4.11', '0.4.12', '0.4.13', '0.4.14',
                                 '0.4.15', '0.4.16', '0.4.17', '0.4.18', '0.4.19',
                                 '0.4.20', '0.4.21', '0.4.22', '0.4.23', '0.4.24']

# 异常均在异常发生时处理，上级传递None结果
Error_list = {
    "error_contract_list": [],
    "slither_error_list": [],
    "complier_error_list": [],
    "unicodeDecode_error_list": [],
    "error_funSig_list": [],
    "extract_model_error": [],
    "lines_key_error_list": [],  # Slither的函数定位问题，比较少见
    "funSig_not_found": []  # 函数签名找不到对应的原函数
}

# 当前合约版本
now_version = "0.4.13"  # 这里可以用正则匹配从合约文本中获取


# 此函数通过读取原文件的函数代码，把修改后的部分还原
# 返回两个字符串，第一个是原字符串，第二个是修改后的字符串
# 返回的两个结果用于在原文中替换
def recovery_fun_code(ori_file_path, line_pos_list):
    ori_line_list = []
    changed_line_list = []
    for line_pos in line_pos_list:
        ori_line_list.append(linecache.getline(ori_file_path, line_pos))
        changed_line_list.append(linecache.getline("./tmp.sol", line_pos))

    ori_text = "".join(ori_line_list)
    changed_text = "".join(changed_line_list)
    # 清空缓存
    linecache.clearcache()
    return ori_text, changed_text


class FunctionCodeBuilder:
    data_files_path = "../test_contracts/"
    output_path = "../tmp_files/ok_contract_files/"

    # 要删除的关键字列表
    remove_word_list = ["payable", "view"]

    # 最终编译通过的合约版本
    final_version_dic = {}

    # 当前处理的合约的信息
    now_file_path = ""
    now_contract_name = ""  # 合约名就是主合约的名字

    def __init__(self):
        self.data_files_path_list = list(get_files_path(self.data_files_path))

    def main(self):
        count = 0
        padding_count = 0
        ok_count = 0

        for file_path in self.data_files_path_list:
            # 进度条显示
            count += 1
            print("{}/{}\t{}/{}".format(ok_count, padding_count, count, self.data_files_path_list.__len__()))
            process_bar(count / self.data_files_path_list.__len__())

            # 处理合约的信息变量
            self.now_file_path = file_path
            self.now_contract_name = self.now_file_path.split("/")[-1].replace(".sol", "")

            # debug
            """
            if self.now_contract_name == "0xcabf96a41a4d98ee91d4fb1004dc4b3b8548cb53":
                a = 0
            else:
                continue
            """

            # 获取slither对原合约的分析结果
            slither_returns = self.get_slither_res()
            if slither_returns is None:
                continue
            else:
                slither_res, main_contract_analysis_res, final_version = \
                    slither_returns[0], slither_returns[1], slither_returns[2]

            padding_count += 1
            # 获得模板代码，如果模板代码返回值为None，说明生成过程有误，记录并跳过此合约
            model_code_str = self.get_code_mould(slither_res, main_contract_analysis_res)
            if model_code_str is None:
                continue
            # 使用模板为每个合约函数生成目标代码
            self.create_code_file_for_function(model_code_str, slither_res, main_contract_analysis_res)
            self.final_version_dic[self.now_contract_name] = final_version

            if os.path.exists(self.output_path + self.now_contract_name):
                ok_count += 1

        pickle.dump(self.final_version_dic, open("../tmp_files/log_pkl/modify_code/final_version.pkl", "wb"))

    def get_slither_res(self):
        """
        :param

        :returns:
        slither_res: slither对合约文件内所有合约的分析结果
        main_contract_analysis_res: slither对合约文件内的主合约的分析结果
        final_version: 合约最终能够编译的版本
        '''
        获得Slither分析结果，根据Slither结果得到生成目标函数CFG的代码
        '''
        """
        # 合约信息
        # 剔除没有版本标识的合约
        final_version = ori_version = now_version
        ori_version_dix = solidity_version_support_list.__len__()

        slither_res = None
        # 使用默认版本的编译器进行编译
        try:
            # 更改solc编译器版本
            os.system('solc-select use {}'.format(ori_version))
            # 使用slither分析函数
            slither_res = Slither(self.now_file_path).contracts
            final_version = ori_version
        # 编码有问题，所以不进行进一步尝试
        except UnicodeDecodeError:
            Error_list["unicodeDecode_error_list"].append(self.now_file_path)
            return None
        # 如果默认版本没有通过编译则使用剩余的所有版本进行尝试
        except SlitherError:
            for idx, try_version in enumerate(solidity_version_support_list):
                # 编译剩余版本时，使循环快进到失败版本之后的版本
                if idx <= ori_version_dix:
                    continue
                try:
                    os.system('solc-select use {}'.format(try_version))
                    slither_res = Slither(self.now_file_path).contracts
                    # 当编译成功时跳出尝试，且记录下编译成功的版本
                    final_version = try_version
                    break
                except SlitherError:
                    continue
                # 多余？？？
                except UnicodeDecodeError:
                    Error_list["unicodeDecode_error_list"].append(self.now_contract_name)
                    return None
        # 基类报错，slither本身分析有误，所以不进行进一步尝试
        except Exception:
            Error_list["slither_error_list"].append(self.now_contract_name)
            return None
        # 尝试所有结果后均无结果，返回None
        if slither_res is None:
            Error_list["complier_error_list"].append(self.now_contract_name)
            return None

        main_contract_analysis_res = None
        for contract_analysis_res in slither_res:
            if contract_analysis_res.name == self.now_contract_name:
                main_contract_analysis_res = contract_analysis_res

        return slither_res, main_contract_analysis_res, final_version

    def get_code_mould(self, slither_res, main_contract_analysis_res):
        """
        读取合约文件内的文本，进行一些粗略修改替换
        ①把"payable", "view"关键字删除；
        ②把所有"public"关键字改成"internal"
        ③把每个合约的构造函数"internal"改成"public"

        :return：
        contract_text：是一个模板字符串，把"payable","view"等关键字剔除，把除构造以外的所有函数的修饰符都改成"internal"

        ‘’‘
        生成模板代码字符串，下一步需要替换对应函数的修饰符为"internal"
        ’‘’
        """

        # 读取合约文件的内容
        f = open(self.now_file_path, "rb")
        # 将换行符统一换成"\n"
        contract_text = f.read().decode("utf-8", errors="ignore").replace("\r\n", "\n")

        #  把合约内没有修饰符的函数都添加internal修饰符
        for contract in slither_res:
            for fun in contract.functions_entry_points:
                # fallback函数删除
                if "fallback()" in fun.full_name:
                    try:
                        contract_text = contract_text.replace(
                            get_lines_by_pos(self.now_file_path, fun.source_mapping["lines"]),
                            "\n" * fun.source_mapping["lines"].__len__())
                    except KeyError:
                        # Slither找不到函数的行定位
                        Error_list["lines_key_error_list"].append(self.now_contract_name + ":" + fun.full_name)
                        continue

                # fallback以外的函数进行替换
                else:
                    try:
                        ori_constructor_text, changed_constructor_text = add_internal_for_functions(
                            self.now_file_path, fun.source_mapping["lines"])
                        contract_text = contract_text.replace(ori_constructor_text, changed_constructor_text)
                    except KeyError:
                        # Slither找不到函数的行定位
                        Error_list["lines_key_error_list"].append(self.now_contract_name + ":" + fun.full_name)
                        continue

        # 删除一些关键字，比如”payable“,"view"
        for remove_word in self.remove_word_list:
            contract_text = contract_text.replace(remove_word, "")
        # 把所有"public"改成"internal"
        contract_text = contract_text.replace("public", "internal")
        # !!!!!!!!!!!!!!!!!!!!!!!! external类型的函数也会生成ABI接口，会影响CFG的提取
        # contract_text = contract_text.replace("external", "internal")

        with open("./tmp.sol", "w", encoding="utf-8") as f:
            f.write(contract_text)

        #  把所有构造函数的"internal"改成"public"
        for contract in slither_res:
            # 非构造函数不去检查
            if contract.constructor is None:
                continue
            else:
                try:
                    ori_constructor_text, changed_constructor_text = \
                        recovery_fun_code(self.now_file_path, contract.constructor.source_mapping["lines"])
                    # 把修改后的构造函数还原
                    # ori表示原始合约函数字符串，changed表示认为修改后的字符串
                    contract_text = contract_text.replace(changed_constructor_text, ori_constructor_text)
                except KeyError:
                    Error_list["lines_key_error_list"].append(self.now_contract_name)
                    return None
        """
        #  把合约的fallback还原
        for fun in main_contract_analysis_res.functions_entry_points:
            if "fallback()" in fun.full_name:
                try:
                    ori_constructor_text, changed_constructor_text = \
                        recovery_fun_code(self.now_file_path, fun.source_mapping["lines"])
                    contract_text = contract_text.replace(changed_constructor_text, ori_constructor_text)
                    break
                except KeyError:
                    Error_list["lines_key_error_list"].append(self.now_contract_name + ":" + fun.full_name)
                    return None
        """

        # 将非继承的合约内容还原
        inheritance_contract_list = list(map(lambda x: x.name, main_contract_analysis_res.inheritance))
        inheritance_contract_list.append(main_contract_analysis_res.name)
        for contract in slither_res:
            if contract.name in inheritance_contract_list:
                continue
            else:
                try:
                    ori_text, changed_text = recovery_fun_code(self.now_file_path, contract.source_mapping["lines"])
                    contract_text = contract_text.replace(changed_text, ori_text)
                except KeyError:
                    Error_list["lines_key_error_list"].append(self.now_contract_name)
                    return None
        # 覆盖写入临时文本文件
        with open("./tmp.sol", "w", encoding="utf-8") as f:
            f.write(contract_text)
        return contract_text

    def create_code_file_for_function(self, code_model_str, slither_res, main_slither_res):
        """
        :param slither_res: slither的全部解析结果
        :param code_model_str: 合约模板代码
        :param main_slither_res:  主合约的slither分析结果

        '''
        使用代码模板生成仅目标函数为public的合约代码，并且保存到为文件，文件名为"地址:函数签名"
        '''
        """

        model_code_file_path = "{}{}/model_contract.sol".format(self.output_path, self.now_contract_name)

        if not os.path.exists(self.output_path + self.now_contract_name):
            os.makedirs(self.output_path + self.now_contract_name)
        with open(model_code_file_path, "w", encoding="utf-8") as f:
            f.write(code_model_str)
        # 此时用slither检测一下模板，如果有问题则会抛出SlitherError异常，说明这个合约不适用
        try:
            _ = Slither(model_code_file_path)
        except SlitherError:
            Error_list["extract_model_error"].append(self.now_contract_name)
            # 删除掉无用的生成结果
            shutil.rmtree(self.output_path + self.now_contract_name)
            return

        ok_count = 0  # 成功合约函数计数
        # 给每一个有历史Gas的函数匹配对应的函数签名
        for slither_fun in main_slither_res.functions:
            fun_name = slither_fun.full_name
            try:
                ori_fun_contract_text, changed_fun_contract_text = recovery_fun_code(
                    self.now_file_path, slither_fun.source_mapping["lines"])
            except KeyError:
                Error_list["lines_key_error_list"].append(self.now_contract_name + ":" + fun_name)
                raise SlitherError
            final_fun_contract_text = code_model_str.replace(changed_fun_contract_text, ori_fun_contract_text)

            # 还原非主合约的与目标函数同名的函数代码,通常是抽象合约的函数声明
            for slither in slither_res:
                # 跳过主合约
                if slither == main_slither_res:
                    continue
                for _slither_fun in slither.functions:
                    if fun_name == _slither_fun.full_name:
                        try:
                            ori_fun_contract_text, changed_fun_contract_text = recovery_fun_code(
                                self.now_file_path, _slither_fun.source_mapping["lines"])
                        except KeyError:
                            raise SlitherError
                        final_fun_contract_text = final_fun_contract_text.replace(changed_fun_contract_text,
                                                                                  ori_fun_contract_text)

            file_save_path = "{}{}/{}.sol".format(self.output_path, self.now_contract_name, slither_fun.name)
            with open(file_save_path, "w", encoding="utf-8") as f:
                f.write(final_fun_contract_text)
            # 使用slither测试编译的目标函数代码
            try:
                _ = Slither(file_save_path)
            except Exception:
                Error_list["error_funSig_list"].append("{}:{}".format(self.now_contract_name, slither_fun.name))
            ok_count += 1
        # 如果都失败了 删除整个中间文件夹
        if ok_count == 0:
            shutil.rmtree(self.output_path + self.now_contract_name)

    """
    后面有空再调整
    def save_log(self):
        pickle.dump(Error_list, open("../data/log_pkl/modify_code/error.pkl", "wb"))
        pickle.dump(self.final_version_dic, open("../data/log_pkl/modify_code/final_version.pkl", "wb"))
        pickle.dump(self.funSig2funName_dic, open("../data/log_pkl/modify_code/funSig2funName_dic.pkl", "wb"))
    """


if __name__ == '__main__':
    c = FunctionCodeBuilder()
    c.main()
    """
    c.save_log()
    """
