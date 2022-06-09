import sha3
import linecache
import os
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import torch
import dill


# 从参数指定的路径下递归获取所有文件的绝对路径
def get_files_path(root_path):
    for root, ds, fs in os.walk(root_path):
        for f in fs:
            fullname = os.path.join(root, f)
            yield fullname


# 遍历获得某个文件夹下所有文件的文件名，min_file滤掉文件数量小于n的最后一层目录
def get_files_path_dic(root_path, min_file=2):
    file_path_dic = {}
    for root, ds, fs in os.walk(root_path):
        # 过滤掉第根目录的结果
        if root == root_path:
            continue
        else:
            # 过滤掉只有模板的合约文件夹
            if fs.__len__() >= min_file:
                file_path_dic[root] = fs
    return file_path_dic


def keccak256(s):
    k = sha3.keccak_256()
    k.update(s.encode("utf-8"))
    return str(hex(eval("0x" + k.hexdigest())))[0:10]


# 此函数通过读取原文件的函数代码，把修改后的部分还原
# 返回两个字符串，第一个是原字符串，第二个是修改后的字符串
# 返回的两个结果用于在原文中替换
def recovery_fun_code(ori_file_path, line_pos_list):
    ori_line_list = []
    changed_line_list = []
    for line_pos in line_pos_list:
        ori_line_list.append(linecache.getline(ori_file_path, line_pos))
        changed_line_list.append(linecache.getline("./tmp_files/tmp.sol", line_pos))

    ori_text = "".join(ori_line_list)
    changed_text = "".join(changed_line_list)
    # 清空缓存
    linecache.clearcache()
    return ori_text, changed_text


def get_lines_by_pos(ori_file_path, line_pos_list):
    line_list = []
    for line_pos in line_pos_list:
        line_list.append(linecache.getline(ori_file_path, line_pos))
    return "".join(line_list)


# 此函数通过读取原文件的函数代码，替换原文件的函数字符串
def add_internal_for_functions(ori_file_path, line_pos_list):
    # 函数修饰符的列表
    function_visibility_specifiers_list = ["public", "private", "external", "internal"]

    line_list = []
    for line_pos in line_pos_list:
        line_list.append(linecache.getline(ori_file_path, line_pos))
    ori_text = "".join(line_list)

    # 截取大括号前的函数声明内容
    declare_text = ori_text.split("{", 1)[0]

    # 判断该函数是否含有函数修饰符
    have_function_visibility_specifiers_flag = False
    for function_visibility_specifiers in function_visibility_specifiers_list:
        if function_visibility_specifiers in declare_text:
            have_function_visibility_specifiers_flag = True
            break
    # 如果不包含修饰符则添加“internal修饰符”
    if not have_function_visibility_specifiers_flag:
        changed_text = ori_text.replace(")", ") internal ", 1)
        return ori_text, changed_text
    else:
        return ori_text, ori_text


# 进度条显示
def process_bar(percent, start_str='', end_str='100%', total_length=30):
    bar = ''.join(["\033[31m%s\033[0m" % '   '] * int(percent * total_length)) + ''
    bar = '\r' + start_str + bar.ljust(total_length) + ' {:0>4.1f}%|'.format(percent * 100) + end_str
    print(bar, end='\n', flush=True)


# 保存错误信息到文本里
def write_error_info_to_text(text_file_path, content):
    with open(text_file_path, "a+", encoding="utf-8") as f:
        f.write(content)
        f.close()


class Painter:
    def __init__(self, fig_output_path):
        self.fig_output_path = fig_output_path
        self.graph_count = 0

    # 将模型输出结果以图的模型
    def draw_heatmap(self, outputs, addFunSig_list):
        draw_bar = tqdm(addFunSig_list)
        print("Start draw graph...")
        i = 0
        with torch.no_grad():
            for addFunSig, _ in zip(addFunSig_list, draw_bar):
                draw_bar.set_description("Draw processing")

                # 读取每个图的预测标签和真实标签
                output = outputs[i].numpy()
                output.resize(1, outputs[0].__len__())
                # 设置图片参数,一个画布放两张heatmap
                plt.rcParams['figure.figsize'] = (12.0, 4.0)
                plt.rcParams['savefig.dpi'] = 1200  # 图片像素
                fig = plt.subplots(nrows=1, ncols=1, figsize=(12, 5))
                sns.heatmap(output, cmap="YlOrBr", yticklabels=False, xticklabels=25, cbar=True)
                fig[0].tight_layout()

                plt.savefig(self.fig_output_path + "{}.png".format(addFunSig))
                self.graph_count += 1
                plt.close()
                # plt.show()
                i += 1
