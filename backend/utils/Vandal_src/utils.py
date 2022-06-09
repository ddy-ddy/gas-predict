import sha3
import linecache
import os
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import dgl
import torch
import string
import collections
import sha3
import re


# from Demo.utils.CFG_Vector_config import *


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


def cut_text(text, lenth):  # lenth 表示切割的子字符串的长度
    textArr = re.findall('.{' + str(lenth) + '}', text)
    textArr.append(text[(len(textArr) * lenth):])
    if textArr[-1] == '': textArr.pop()
    return textArr


def update_dict(A, B):
    for key, value in B.items():
        if key in A:
            A[key] += value
        else:
            A[key] = value
    return A


def create_dgl_object(dis_node_list, node_add2id_dic):
    # 添加边的关系
    edge_pair_list = []

    # 添加控制流的边,只从后继关系中提取出边
    for block in dis_node_list:
        for succs_node in block.succs:
            edge_pair_list.append([node_add2id_dic[block.evm_ops[0].__str__().split(" ")[0]],
                                   node_add2id_dic[succs_node.evm_ops[0].__str__().split(" ")[0]]])
    # 节点的组合构成边
    u, v = [i[0] for i in edge_pair_list], [j[1] for j in edge_pair_list]
    dgl_graph = dgl.graph((torch.tensor(u), torch.tensor(v)))
    return dgl_graph


def modify_op_code_list(op_code_list):
    del_op_code_list = ["DUP", "SWAP", "POP"]

    new_op_cdoe_list = []
    for ori_op_code in op_code_list:
        del_flag = False
        for del_op_code in del_op_code_list:
            if ori_op_code.strip(string.digits) in del_op_code:
                del_flag = True
                break
        if del_flag:
            continue
        if "PUSH" in ori_op_code:
            new_op_cdoe_list.append("CONST")
        else:
            new_op_cdoe_list.append(ori_op_code.strip(string.digits))
    if not new_op_cdoe_list:
        return ["NOP"]
    return new_op_cdoe_list


def embeding_nodes(graph, blocks_op_codes_list, node_add_list):
    opCode_feature = []
    strengthen_feature = []
    strengthen_feature1 = []
    specialOP_feature = []
    for block_op_codes_list in blocks_op_codes_list:
        node_opCode_feature = [0.] * op_2Id_dic.__len__()
        # 操作码向量
        op_nodes_count_dic = collections.Counter(block_op_codes_list)
        for item in op_nodes_count_dic.items():
            try:
                node_opCode_feature[op_2Id_dic[item[0]]] = item[1]
            except Exception as e:
                print(e)
                pass
        opCode_feature.append(node_opCode_feature)

        # 强化向量 one-hot类型
        node_strengthen_feature = [0.] * attrNum * 2
        block_attr_set = set(block_op_codes_list) & attrIdxDic.keys()  # 取交集
        # 如果没有特殊操作，那么该节点就是Common属性
        if block_attr_set.__len__() == 0:
            block_attr_set = {"COMMON"}
        # 强化的one-hot向量，每拥有1种属性对应两个位置的1
        for block_attr in block_attr_set:
            node_strengthen_feature[attrIdxDic[block_attr] * 2], \
            node_strengthen_feature[attrIdxDic[block_attr] * 2 + 1] = 1., 1.
        node_strengthen_feature = np.array(node_strengthen_feature, dtype=np.float32)
        strengthen_feature.append(node_strengthen_feature)

        # 强化向量 12维哈希类型
        block_attr_set = set(block_op_codes_list) & attrIdxDic.keys()  # 取交集
        if block_attr_set.__len__() == 0:
            block_attr_set = {"COMMON"}
        k = sha3.sha3_256()
        k.update(str(block_attr_set).encode("utf-8"))
        hash_result = k.hexdigest()
        tmp = cut_text(hash_result, 4)[:attrNum * 2]
        node_strengthen_feature1 = [eval("0x" + i) for i in tmp]
        node_strengthen_feature1 = np.array(node_strengthen_feature1, dtype=np.float32)
        strengthen_feature1.append(node_strengthen_feature1)

        # 特殊操作码向量
        node_specialOP_feature = [0.] * particularOPIdxDic.__len__()
        specailOp_codes_count_dic = dict(collections.Counter(block_op_codes_list))

        for item in specailOp_codes_count_dic.items():
            if item[0] in particularOPIdxDic:
                node_specialOP_feature[particularOPIdxDic[item[0]]] = item[1]
        specialOP_feature.append(node_specialOP_feature)

    graph.ndata["opCode_feature"] = torch.tensor(np.array(opCode_feature, dtype=np.float32))
    graph.ndata["strengthen_feature"] = torch.tensor(np.array(strengthen_feature, dtype=np.float32))
    graph.ndata["strengthen_feature1"] = torch.tensor(np.array(strengthen_feature1, dtype=np.float32))
    graph.ndata["spOPcode_feature"] = torch.tensor(np.array(specialOP_feature, dtype=np.float32))
    # 用于子图解释
    graph.ndata["node_add_list"] = torch.tensor(np.array(list(map(lambda x: int(x, 16), node_add_list)), dtype=np.int))
    return graph


def create_graph_from_cfg(cfg):
    dis_node_list = []
    # 判断选择函数的节点是否已经找齐
    find_all_flag = False
    for block in cfg.blocks:
        # 没有对应函数的节点，可能是选择函数也可能是Vandal没有找到对应函数的节点
        # 所以先筛选掉选择函数的节点后，全部归属到目标函数
        if (block.ident_suffix == "") and (not find_all_flag):
            continue
        elif "_F1" not in block.ident_suffix:
            find_all_flag = True
            dis_node_list.append(block)

    # 节点的地址到id的映射字典
    node_add2id_dic = {}
    node_count = 0
    # 节点特征列表
    nodes_op_codes_list = []

    for block in dis_node_list:
        node_add2id_dic[block.evm_ops[0].__str__().split(" ")[0]] = node_count
        ori_op_codes_list = [op_code.__str__().split(" ", 1)[-1] for op_code in block.evm_ops]
        # 如果节点的操作码数量为0或者Vandal解析错误（INVALID）
        if ori_op_codes_list.__len__() == 0 and "INVALID" in ori_op_codes_list:
            nodes_op_codes_list.append(["INVALID"])
        else:
            # 操作码需要修改一下，比如ADDX，PUSHX等进行合并、删除一些操作码比如DUP、SWAP
            nodes_op_codes_list.append(modify_op_code_list(ori_op_codes_list))
        node_count += 1
    # 根据边的关系构建DGL的图数据（未嵌入节点特征）
    graph = create_dgl_object(dis_node_list, node_add2id_dic)

    # 节点特征嵌入
    graph = embeding_nodes(graph, nodes_op_codes_list, list(node_add2id_dic.keys()))

    return graph
