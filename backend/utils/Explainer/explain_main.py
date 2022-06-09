import os
import sys
import torch
from dig.xgraph.method.subgraphx import find_closest_node_result
from torch_geometric.data import DataLoader # 这行不能删

sys.path.append("../../")
# from backend.utils.Explainer.config import *
from backend.utils.model import GIN
from backend.utils.Explainer.subgraphX import SubgraphX
from bs4 import BeautifulSoup
import re


class Explainer:
    def __init__(self, dataset, addFunSig_list, pre_list, model, device):
        self.dataset = dataset
        self.addFunSig_list = addFunSig_list
        self.pre_list = pre_list
        self.device = device
        self.explain_target_top_K = 1       # 选概率最大的那个区间解释
        self.model = model
        self.model.explain = True
        self.output_dim = self.dataset.get(0).y.shape[0]

        self.org_cfg_path = "../tmp_files/cfg_build/{}/{}/cfg.html"
        self.output_path = "../output/cfg_marked/{}.html"

    def draw_cfg_html(self, addFunAndSig, node_add_list, fill_color="#66CCFF"):
        tmp = addFunAndSig.split(":")
        add = tmp[0]
        funSig = tmp[1]
        soup = BeautifulSoup(open(self.org_cfg_path.format(add, funSig)), "html5lib")

        for node_add in node_add_list:
            ellipse_tag = soup.find("g", attrs={"id": re.compile(r"{}".format(node_add)), "class": ""}).find("ellipse")
            ellipse_tag.attrs["fill"] = fill_color

        with open(self.output_path.format(addFunAndSig),
                  "w", encoding="utf-8") as f:
            f.write(soup.prettify())

    def main(self):
        for data_idx in range(self.dataset.len()):
            data = self.dataset.get(data_idx)
            max_nodes = int(data.num_nodes / 3)

            explainer = SubgraphX(self.model, num_classes=self.output_dim, device=self.device, explain_graph=True,
                                  reward_method='mc_l_shapley', explain_target_top_K=self.explain_target_top_K,
                                  save_dir="./explain_result", field=True)
            _, explanation_results, related_preds = explainer(x=data.x, edge_index=data.edge_index,
                                                              node_idx=None, max_nodes=max_nodes,
                                                              addFunSig=data.addFunSig)

            for i in range(self.explain_target_top_K):
                # 提取最相关的子图，子图的节点数量小于等于max_nodes
                result = find_closest_node_result(explanation_results[i], max_nodes=max_nodes)
                sub_nodes_id_list = result.coalition
                nodes_add_list = data.node_add_list

                # 在原始的cfg上标注解释节点
                sub_nodes_add_list = [nodes_add_list[i] for i in sub_nodes_id_list]
                self.draw_cfg_html(data.addFunSig, sub_nodes_add_list)
