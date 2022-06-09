import math
import copy
import torch
import numpy as np
import networkx as nx
from rdkit import Chem
from torch import Tensor
from textwrap import wrap
from functools import partial
from collections import Counter
import torch.nn.functional as F
from typing import List, Tuple, Dict
from torch_geometric.data import Batch, Data
from torch_geometric.utils import to_networkx
from typing import Callable, Union, Optional
import matplotlib.pyplot as plt
from torch_geometric.utils.num_nodes import maybe_num_nodes
from torch_geometric.nn.conv import MessagePassing
from torch_geometric.datasets import MoleculeNet
from dig.xgraph.method.shapley import GnnNetsGC2valueFunc, \
    gnn_score, mc_shapley, l_shapley, mc_l_shapley, NC_mc_l_shapley

sum_d = 0


def find_closest_node_result(results, max_nodes):
    """ return the highest reward tree_node with its subgraph is smaller than max_nodes """

    results = sorted(results, key=lambda x: len(x.coalition))

    result_node = results[0]
    for result_idx in range(len(results)):
        x = results[result_idx]
        if len(x.coalition) <= max_nodes and x.P > result_node.P:
            result_node = x
    return result_node


def reward_func(reward_method, value_func, node_idx=None,
                local_radius=4, sample_num=100,
                subgraph_building_method='zero_filling'):
    if reward_method.lower() == 'gnn_score':
        return partial(gnn_score,
                       value_func=value_func,
                       subgraph_building_method=subgraph_building_method)

    elif reward_method.lower() == 'mc_shapley':
        return partial(mc_shapley,
                       value_func=value_func,
                       subgraph_building_method=subgraph_building_method,
                       sample_num=sample_num)

    elif reward_method.lower() == 'l_shapley':
        return partial(l_shapley,
                       local_radius=local_radius,
                       value_func=value_func,
                       subgraph_building_method=subgraph_building_method)

    elif reward_method.lower() == 'mc_l_shapley':
        return partial(mc_l_shapley,
                       local_radius=local_radius,
                       value_func=value_func,
                       subgraph_building_method=subgraph_building_method,
                       sample_num=sample_num)

    elif reward_method.lower() == 'nc_mc_l_shapley':
        assert node_idx is not None, " Wrong node idx input "
        return partial(NC_mc_l_shapley,
                       node_idx=node_idx,
                       local_radius=local_radius,
                       value_func=value_func,
                       subgraph_building_method=subgraph_building_method,
                       sample_num=sample_num)

    else:
        raise NotImplementedError


def k_hop_subgraph_with_default_whole_graph(
        edge_index, node_idx=None, num_hops=3, relabel_nodes=False,
        num_nodes=None, flow='source_to_target'):
    r"""Computes the :math:`k`-hop subgraph of :obj:`edge_index` around node
    :attr:`node_idx`.
    It returns (1) the nodes involved in the subgraph, (2) the filtered
    :obj:`edge_index` connectivity, (3) the mapping from node indices in
    :obj:`node_idx` to their new location, and (4) the edge mask indicating
    which edges were preserved.
    Args:
        node_idx (int, list, tuple or :obj:`torch.Tensor`): The central
            node(s).
        num_hops: (int): The number of hops :math:`k`.
        edge_index (LongTensor): The edge indices.
        relabel_nodes (bool, optional): If set to :obj:`True`, the resulting
            :obj:`edge_index` will be relabeled to hold consecutive indices
            starting from zero. (default: :obj:`False`)
        num_nodes (int, optional): The number of nodes, *i.e.*
            :obj:`max_val + 1` of :attr:`edge_index`. (default: :obj:`None`)
        flow (string, optional): The flow direction of :math:`k`-hop
            aggregation (:obj:`"source_to_target"` or
            :obj:`"target_to_source"`). (default: :obj:`"source_to_target"`)
    :rtype: (:class:`LongTensor`, :class:`LongTensor`, :class:`LongTensor`,
             :class:`BoolTensor`)
    """

    num_nodes = maybe_num_nodes(edge_index, num_nodes)

    assert flow in ['source_to_target', 'target_to_source']
    if flow == 'target_to_source':
        row, col = edge_index
    else:
        col, row = edge_index  # edge_index 0 to 1, col: source, row: target

    node_mask = row.new_empty(num_nodes, dtype=torch.bool)
    edge_mask = row.new_empty(row.size(0), dtype=torch.bool)

    inv = None

    if node_idx is None:
        subsets = torch.tensor([0])
        cur_subsets = subsets
        while 1:
            node_mask.fill_(False)
            node_mask[subsets] = True
            torch.index_select(node_mask, 0, row, out=edge_mask)
            subsets = torch.cat([subsets, col[edge_mask]]).unique()
            if not cur_subsets.equal(subsets):
                cur_subsets = subsets
            else:
                subset = subsets
                break
    else:
        if isinstance(node_idx, (int, list, tuple)):
            node_idx = torch.tensor([node_idx], device=row.device, dtype=torch.int64).flatten()
        elif isinstance(node_idx, torch.Tensor) and len(node_idx.shape) == 0:
            node_idx = torch.tensor([node_idx])
        else:
            node_idx = node_idx.to(row.device)

        subsets = [node_idx]
        for _ in range(num_hops):
            node_mask.fill_(False)
            node_mask[subsets[-1]] = True
            torch.index_select(node_mask, 0, row, out=edge_mask)
            subsets.append(col[edge_mask])
        subset, inv = torch.cat(subsets).unique(return_inverse=True)
        inv = inv[:node_idx.numel()]

    node_mask.fill_(False)
    node_mask[subset] = True
    edge_mask = node_mask[row] & node_mask[col]

    edge_index = edge_index[:, edge_mask]

    if relabel_nodes:
        node_idx = row.new_full((num_nodes,), -1)
        node_idx[subset] = torch.arange(subset.size(0), device=row.device)
        edge_index = node_idx[edge_index]

    return subset, edge_index, inv, edge_mask  # subset: key new node idx; value original node idx


def compute_scores(score_func, children):
    results = []
    for child in children:
        if child.P == 0:  # 没计算过分数的节点才计算label分数
            score = score_func(child.coalition, child.data)
        else:
            score = child.P
        results.append(score)
    return results  # 得到每个子节点的分数


class PlotUtils(object):
    def __init__(self, dataset_name):
        self.dataset_name = dataset_name

    def plot(self, graph, nodelist, figname, **kwargs):
        """ plot function for different dataset """
        if self.dataset_name.lower() in ['ba_2motifs', 'ba_lrp']:
            self.plot_ba2motifs(graph, nodelist, figname=figname)
        elif self.dataset_name.lower() in ['mutag'] + list(MoleculeNet.names.keys()):
            x = kwargs.get('x')
            self.plot_molecule(graph, nodelist, x, figname=figname)
        elif self.dataset_name.lower() in ['ba_shapes', 'ba_shapes', 'tree_grid', 'tree_cycle']:
            y = kwargs.get('y')
            node_idx = kwargs.get('node_idx')
            self.plot_bashapes(graph, nodelist, y, node_idx, figname=figname)
        elif self.dataset_name.lower() in ['Graph-SST2'.lower()]:
            words = kwargs.get('words')
            self.plot_sentence(graph, nodelist, words=words, figname=figname)
        else:
            raise NotImplementedError

    @staticmethod
    def plot_subgraph(graph, nodelist, colors: Union[list, str] = '#FFA500', labels=None, edge_color='gray',
                      edgelist=None, subgraph_edge_color='black', title_sentence=None, figname=None):

        if edgelist is None:
            edgelist = [(n_frm, n_to) for (n_frm, n_to) in graph.edges()
                        if n_frm in nodelist and n_to in nodelist]
        pos = nx.kamada_kawai_layout(graph)
        pos_nodelist = {k: v for k, v in pos.items() if k in nodelist}

        nx.draw_networkx_nodes(graph, pos,
                               nodelist=list(graph.nodes()),
                               node_color=colors,
                               node_size=300)

        nx.draw_networkx_edges(graph, pos, width=3, edge_color=edge_color, arrows=False)

        nx.draw_networkx_edges(graph, pos=pos_nodelist,
                               edgelist=edgelist, width=6,
                               edge_color=subgraph_edge_color,
                               arrows=False)

        if labels is not None:
            nx.draw_networkx_labels(graph, pos, labels)

        plt.axis('off')
        if figname is not None:
            plt.savefig(figname)
        if title_sentence is not None:
            plt.title('\n'.join(wrap(title_sentence, width=60)))
        plt.show()

    @staticmethod
    def plot_subgraph_with_nodes(graph, nodelist, node_idx, colors: Union[str, list] = '#FFA500',
                                 labels=None, edge_color='gray', edgelist=None,
                                 subgraph_edge_color='black', title_sentence=None, figname=None):
        node_idx = int(node_idx)
        if edgelist is None:
            edgelist = [(n_frm, n_to) for (n_frm, n_to) in graph.edges()
                        if n_frm in nodelist and n_to in nodelist]

        pos = nx.kamada_kawai_layout(graph)  # calculate according to graph.nodes()
        pos_nodelist = {k: v for k, v in pos.items() if k in nodelist}

        nx.draw_networkx_nodes(graph, pos,
                               nodelist=list(graph.nodes()),
                               node_color=colors,
                               node_size=300)
        if isinstance(colors, list):
            list_indices = int(np.where(np.array(graph.nodes()) == node_idx)[0])
            node_idx_color = colors[list_indices]
        else:
            node_idx_color = colors

        nx.draw_networkx_nodes(graph, pos=pos,
                               nodelist=[node_idx],
                               node_color=node_idx_color,
                               node_size=600)

        nx.draw_networkx_edges(graph, pos, width=3, edge_color=edge_color, arrows=False)

        nx.draw_networkx_edges(graph, pos=pos_nodelist,
                               edgelist=edgelist, width=3,
                               edge_color=subgraph_edge_color,
                               arrows=False)

        if labels is not None:
            nx.draw_networkx_labels(graph, pos, labels)

        plt.axis('off')
        if figname is not None:
            plt.savefig(figname)
        if title_sentence is not None:
            plt.title('\n'.join(wrap(title_sentence, width=60)))
        plt.show()

    @staticmethod
    def plot_sentence(graph, nodelist, words, edgelist=None, figname=None):
        pos = nx.kamada_kawai_layout(graph)
        words_dict = {i: words[i] for i in graph.nodes}
        if nodelist is not None:
            pos_coalition = {k: v for k, v in pos.items() if k in nodelist}
            nx.draw_networkx_nodes(graph, pos_coalition,
                                   nodelist=nodelist,
                                   node_color='yellow',
                                   node_shape='o',
                                   node_size=500)
            if edgelist is None:
                edgelist = [(n_frm, n_to) for (n_frm, n_to) in graph.edges()
                            if n_frm in nodelist and n_to in nodelist]
                nx.draw_networkx_edges(graph, pos=pos_coalition, edgelist=edgelist, width=5, edge_color='yellow')

        nx.draw_networkx_nodes(graph, pos, nodelist=list(graph.nodes()), node_size=300)

        nx.draw_networkx_edges(graph, pos, width=2, edge_color='grey')
        nx.draw_networkx_labels(graph, pos, words_dict)

        plt.axis('off')
        plt.title('\n'.join(wrap(' '.join(words), width=50)))
        if figname is not None:
            plt.savefig(figname)
        plt.close('all')

    def plot_ba2motifs(self, graph, nodelist, edgelist=None, figname=None):
        return self.plot_subgraph(graph, nodelist, edgelist=edgelist, figname=figname)

    def plot_molecule(self, graph, nodelist, x, edgelist=None, figname=None):
        # collect the text information and node color
        if self.dataset_name == 'mutag':
            node_dict = {0: 'C', 1: 'N', 2: 'O', 3: 'F', 4: 'I', 5: 'Cl', 6: 'Br'}
            node_idxs = {k: int(v) for k, v in enumerate(np.where(x.cpu().numpy() == 1)[1])}
            node_labels = {k: node_dict[v] for k, v in node_idxs.items()}
            node_color = ['#E49D1C', '#4970C6', '#FF5357', '#29A329', 'brown', 'darkslategray', '#F0EA00']
            colors = [node_color[v % len(node_color)] for k, v in node_idxs.items()]

        elif self.dataset_name in MoleculeNet.names.keys():
            element_idxs = {k: int(v) for k, v in enumerate(x[:, 0])}
            node_idxs = element_idxs
            node_labels = {k: Chem.PeriodicTable.GetElementSymbol(Chem.GetPeriodicTable(), int(v))
                           for k, v in element_idxs.items()}
            node_color = ['#29A329', 'lime', '#F0EA00', 'maroon', 'brown', '#E49D1C', '#4970C6', '#FF5357']
            colors = [node_color[(v - 1) % len(node_color)] for k, v in node_idxs.items()]
        else:
            raise NotImplementedError

        self.plot_subgraph(graph, nodelist, colors=colors, labels=node_labels,
                           edgelist=edgelist, edge_color='gray',
                           subgraph_edge_color='black',
                           title_sentence=None, figname=figname)

    def plot_bashapes(self, graph, nodelist, y, node_idx, edgelist=None, figname=None):
        node_idxs = {k: int(v) for k, v in enumerate(y.reshape(-1).tolist())}
        node_color = ['#FFA500', '#4970C6', '#FE0000', 'green']
        colors = [node_color[v % len(node_color)] for k, v in node_idxs.items()]
        self.plot_subgraph_with_nodes(graph, nodelist, node_idx, colors,
                                      edgelist=edgelist,
                                      figname=figname,
                                      subgraph_edge_color='black')


class MCTSNodeD(object):

    def __init__(self, coalition: list, data: Data, ori_graph: nx.Graph, domain_map: {},
                 c_puct: float = 10.0, W: float = 0, N: int = 0, P: float = 0):
        self.data = data
        self.rollout_num = 0
        self.coalition = coalition
        self.ori_graph = ori_graph
        self.c_puct = c_puct
        self.children = []
        self.domain_map = domain_map
        self.W = W  # sum of node value
        self.N = N  # times of arrival
        self.P = P  # property score (reward)
        self.f = 0.0
        self.s = 0.0
        for i in self.coalition:
            if self.domain_map[i] == 0:
                self.f = self.f + 1
                self.s = self.s + 1
            else:
                self.s = self.s + 1
        self.D = self.f / self.s
        global sum_d
        sum_d += self.D

    def Q(self):
        return self.W / self.N if self.N > 0 else 0

    def U(self, n):
        return self.c_puct * self.P * math.sqrt(n) / (1 + self.N) * self.D

    def D(self):
        return self.f / self.s


class MCTSNode(object):
    def __init__(self, coalition: list, data: Data, ori_graph: nx.Graph, domain_map: {},
                 c_puct: float = 10.0, W: float = 0, N: int = 0, P: float = 0):
        self.data = data
        self.rollout_num = 0
        self.coalition = coalition
        self.ori_graph = ori_graph
        self.c_puct = c_puct
        self.children = []
        self.domain_map = domain_map
        self.W = W  # sum of node value
        self.N = N  # times of arrival
        self.P = P  # property score (reward)
        self.f = 0.0
        self.s = 0.0
        for i in self.coalition:
            if self.domain_map[i] == 0:
                self.f = self.f + 1
                self.s = self.s + 1
            else:
                self.s = self.s + 1
        self.D = self.f / self.s
        global sum_d
        sum_d += self.D

    def Q(self):
        return self.W / self.N if self.N > 0 else 0

    def U(self, n):
        return self.c_puct * self.P * math.sqrt(n) / (1 + self.N)


class MCTS(object):
    r"""
    Monte Carlo Tree Search Method

    Args:
        X (:obj:`torch.Tensor`): Input node features
        edge_index (:obj:`torch.Tensor`): The edge indices.
        num_hops (:obj:`int`): The number of hops :math:`k`.
        n_rollout (:obj:`int`): The number of sequence to build the monte carlo tree.
        min_atoms (:obj:`int`): The number of atoms for the subgraph in the monte carlo tree leaf node.
        c_puct (:obj:`float`): The hyper-parameter to encourage exploration while searching.
        expand_atoms (:obj:`int`): The number of children to expand.
        high2low (:obj:`bool`): Whether to expand children tree node from high degree nodes to low degree nodes.
        node_idx (:obj:`int`): The target node index to extract the neighborhood.
        score_func (:obj:`Callable`): The reward function for tree node, such as mc_shapely and mc_l_shapely.

    """

    def __init__(self, X: torch.Tensor, edge_index: torch.Tensor, num_hops: int,
                 n_rollout: int = 10, min_atoms: int = 3, c_puct: float = 10.0,
                 expand_atoms: int = 14, high2low: bool = False, field = False,
                 node_idx: int = None, score_func: Callable = None):

        # 在MCTS搜索树中构建了一个图数据对象data
        self.X = X
        self.rollout_num = 0
        self.edge_index = edge_index
        self.num_hops = num_hops
        self.data = Data(x=self.X, edge_index=self.edge_index)
        self.field = field

        # yxx
        self.domain_map = {}
        for i, x in enumerate(self.X):
            if x[66:75].sum() == 0 and x[-2].sum() == 0:
                self.domain_map[i] = 0
            else:
                self.domain_map[i] = 1

        # 默认是生成无向图，测试使用有向图
        # self.graph = to_networkx(self.data, to_undirected=True)
        self.graph = to_networkx(self.data, to_undirected=False)
        self.data = Batch.from_data_list([self.data])
        self.num_nodes = self.graph.number_of_nodes()
        self.score_func = score_func
        self.n_rollout = n_rollout
        self.min_atoms = min_atoms  # 最小子图节点数量
        self.c_puct = c_puct
        self.expand_atoms = expand_atoms
        self.high2low = high2low

        # extract the sub-graph and change the node indices.  对图分类结果进行解释则node_idx为None
        if node_idx is not None:
            self.ori_node_idx = node_idx
            self.ori_graph = copy.copy(self.graph)
            x, edge_index, subset, edge_mask, kwargs = \
                self.__subgraph__(node_idx, self.X, self.edge_index, self.num_hops)
            self.data = Batch.from_data_list([Data(x=x, edge_index=edge_index)])
            self.graph = self.ori_graph.subgraph(subset.tolist())
            mapping = {int(v): k for k, v in enumerate(subset)}
            self.graph = nx.relabel_nodes(self.graph, mapping)
            self.node_idx = torch.where(subset == self.ori_node_idx)[0]
            self.num_nodes = self.graph.number_of_nodes()
            self.subset = subset

        self.root_coalition = sorted([node for node in range(self.num_nodes)])  # 根节点的节点目录数量
        if self.field:
            # 重新封装了个函数MCTSNodeClass，这个函数用于生成一个MCTS搜索树的节点，参数的值指向MCTS树的内部变量,此时唯一的输入参数为节点序号的目录
            self.MCTSNodeClass = partial(MCTSNodeD, data=self.data, ori_graph=self.graph, c_puct=self.c_puct,
                                         domain_map=self.domain_map)
        else:
            self.MCTSNodeClass = partial(MCTSNode, data=self.data, ori_graph=self.graph, c_puct=self.c_puct,
                                         domain_map=self.domain_map)

        self.root = self.MCTSNodeClass(self.root_coalition)  # 创建第一个节点作为搜索树的根节点
        self.state_map = {str(self.root.coalition): self.root}  # 映射字典，节点组合字符串到节点的映射字典

    def set_score_func(self, score_func):
        self.score_func = score_func

    @staticmethod
    def __subgraph__(node_idx, x, edge_index, num_hops, **kwargs):
        num_nodes, num_edges = x.size(0), edge_index.size(1)
        subset, edge_index, _, edge_mask = k_hop_subgraph_with_default_whole_graph(
            edge_index, node_idx, num_hops, relabel_nodes=True, num_nodes=num_nodes)

        x = x[subset]
        for key, item in kwargs.items():
            if torch.is_tensor(item) and item.size(0) == num_nodes:
                item = item[subset]
            elif torch.is_tensor(item) and item.size(0) == num_edges:
                item = item[edge_mask]
            kwargs[key] = item

        return x, edge_index, subset, edge_mask, kwargs

    def mcts_rollout(self, tree_node):
        cur_graph_coalition = tree_node.coalition  # 当前搜索树节点的节点序号组
        # 如果裁剪后的子树的节点数量小于或等于min_atoms，则停止递归rollout
        if len(cur_graph_coalition) <= self.min_atoms:
            return tree_node.P

        # Expand if this node has never been visited，这里根据节点的子节点数量来判断节点是否被访问？
        if len(tree_node.children) == 0:
            # 图的连接边组列表。例如：[(0, 3), (1, 3)]
            node_degree_list = list(self.graph.subgraph(cur_graph_coalition).degree)
            # 按节点的度排序
            node_degree_list = sorted(node_degree_list, key=lambda x: x[1], reverse=self.high2low)
            all_nodes = [x[0] for x in node_degree_list]  # 前继节点的列表
            # 判断需要拓展的子节点序号由当前所有前继节点截取获，数量由参数决定
            if len(all_nodes) < self.expand_atoms:
                expand_nodes = all_nodes
            else:
                expand_nodes = all_nodes[:self.expand_atoms]
            # 遍历每一个需要拓展的节点，即移除拓展节点后生成的子图
            for each_node in expand_nodes:
                # for each node, pruning it and get the remaining sub-graph
                # here we check the resulting sub-graphs and only keep the largest one
                subgraph_coalition = [node for node in all_nodes if node != each_node]  # 剔除掉拓展的目标节点的节点序号序列

                # 反正下面这段的作用是提取原图剔除了目标节点的最大连通子图，
                # 建立一个连通子图序列
                subgraphs = [self.graph.subgraph(c)
                             for c in nx.weakly_connected_components(self.graph.subgraph(subgraph_coalition))]
                main_sub = subgraphs[0]

                for sub in subgraphs:
                    if sub.number_of_nodes() > main_sub.number_of_nodes():
                        main_sub = sub

                new_graph_coalition = sorted(list(main_sub.nodes()))

                # check the state map and merge the same sub-graph
                find_same = False
                for old_graph_node in self.state_map.values():
                    if Counter(old_graph_node.coalition) == Counter(new_graph_coalition):
                        new_node = old_graph_node
                        find_same = True
                # 如果没有找到相同的子图，那么就把这结果合并到 MCTS树的记录字典state_map里
                if not find_same:
                    new_node = self.MCTSNodeClass(new_graph_coalition)
                    new_node.rollout_num = self.rollout_num
                    self.state_map[str(new_graph_coalition)] = new_node
                # 判断子节点是否与自己相同，如果不相同则作为自己的
                find_same_child = False
                for cur_child in tree_node.children:
                    if Counter(cur_child.coalition) == Counter(new_graph_coalition):
                        find_same_child = True

                if not find_same_child:
                    tree_node.children.append(new_node)
            # 得到每个子节点的分数，并把这个分数写入到子节点的状态变量里
            scores = compute_scores(self.score_func, tree_node.children)
            for child, score in zip(tree_node.children, scores):
                child.P = score

        sum_count = sum([c.N for c in tree_node.children])  # 统计所有子节点的到达(被搜索)次数
        if self.field:
            selected_node = max(tree_node.children, key=lambda x: x.Q() + x.U(sum_count) + x.D)
        else:
            selected_node = max(tree_node.children, key=lambda x: x.Q() + x.U(sum_count))
        v = self.mcts_rollout(selected_node)
        selected_node.W += v
        selected_node.N += 1
        return v  # -0.16905923187732697

    def mcts(self, verbose=True):
        if verbose:
            print(f"The nodes in graph is {self.graph.number_of_nodes()}")
        # 迭代n_rollout次,也就是产生这么多颗搜索树,当树的规模比较小时，第一次以外的搜索无法发现新的节点。
        for rollout_idx in range(self.n_rollout):
            self.mcts_rollout(self.root)  #
            if verbose:
                print(f"At the {rollout_idx} rollout, {len(self.state_map)} states that have been explored.")
            self.rollout_num += 1

        explanations = [node for _, node in self.state_map.items()]
        explanations = sorted(explanations, key=lambda x: x.P, reverse=True)
        return explanations

        # W sum of node value
        # N times of arrival
        # P property score (reward)


class SubgraphX(object):
    r"""
    The implementation of paper
    `On Explainability of Graph Neural Networks via Subgraph Explorations <https://arxiv.org/abs/2102.05152>`_.

    Args:
        model (:obj:`torch.nn.Module`): The target model prepared to explain
        num_classes(:obj:`int`): Number of classes for the datasets
        num_hops(:obj:`int`, :obj:`None`): The number of hops to extract neighborhood of target node
          (default: :obj:`None`)
        explain_graph(:obj:`bool`): Whether to explain graph classification model (default: :obj:`True`)
         rollout(:obj:`int`): Number of iteration to get the prediction #获得预测的迭代次数
        min_atoms(:obj:`int`): Number of atoms of the leaf node in search tree # 搜素树中叶节点的原子树（节点是要解释的智能合约，而叶子就是我的子图）
        c_puct(:obj:`float`): The hyperparameter which encourages the exploration
        expand_atoms(:obj:`int`): The number of atoms to expand
          when extend the child nodes in the search tree
        high2low(:obj:`bool`): Whether to expand children nodes from high degree to low degree when
          extend the child nodes in the search tree (default: :obj:`False`)
        local_radius(:obj:`int`): Number of local radius to calculate :obj:`l_shapley`, :obj:`mc_l_shapley`
        sample_num(:obj:`int`): Sampling time of monte carlo sampling approximation for
          :obj:`mc_shapley`, :obj:`mc_l_shapley` (default: :obj:`mc_l_shapley`)
        reward_method(:obj:`str`): The command string to select the
        subgraph_building_method(:obj:`str`): The command string for different subgraph building method,
          such as :obj:`zero_filling`, :obj:`split` (default: :obj:`zero_filling`)
        save_dir(:obj:`str`, :obj:`None`): Root directory to save the explanation results (default: :obj:`None`)
        filename(:obj:`str`): The filename of results
        vis(:obj:`bool`): Whether to show the visualization (default: :obj:`True`)
    """
    """
    Example:
        >>> # For graph classification task
        >>> subgraphx = SubgraphX(model=model, num_classes=2)
        >>> _, explanation_results, related_preds = subgraphx(x, edge_index)

    """

    def __init__(self, model, num_classes: int, device, num_hops: Optional[int] = None, explain_graph: bool = True,
                 rollout: int = 4, min_atoms: int = 3, c_puct: float = 10.0, expand_atoms=14,
                 high2low=False, local_radius=4, sample_num=100, reward_method='mc_l_shapley',
                 subgraph_building_method='zero_filling', save_dir: Optional[str] = None, field=False,
                 filename: str = 'example', vis: bool = True, explain_target_top_K=5):

        self.model = model
        self.model.eval()
        self.device = device
        self.num_classes = num_classes
        self.num_hops = self.update_num_hops(num_hops)
        self.explain_graph = explain_graph
        self.explain_target_top_K = explain_target_top_K  # 解析最大概率的K个Label
        self.field = field
        self.sum_d = 0

        # mcts hyper-parameters
        self.rollout = rollout
        self.min_atoms = min_atoms
        self.c_puct = c_puct
        self.expand_atoms = expand_atoms
        self.high2low = high2low

        # reward function hyper-parameters
        self.local_radius = local_radius
        self.sample_num = sample_num
        self.reward_method = reward_method
        self.subgraph_building_method = subgraph_building_method

        # saving and visualization
        self.vis = vis
        self.save_dir = save_dir
        self.filename = filename
        self.save = True if self.save_dir is not None else False

    def update_num_hops(self, num_hops):
        if num_hops is not None:
            return num_hops

        k = 0
        for module in self.model.modules():
            if isinstance(module, MessagePassing):
                k += 1
        return k

    def get_reward_func(self, value_func, node_idx=None):
        if self.explain_graph:
            node_idx = None
        else:
            assert node_idx is not None
        return reward_func(reward_method=self.reward_method,
                           value_func=value_func,
                           node_idx=node_idx,
                           local_radius=self.local_radius,
                           sample_num=self.sample_num,
                           subgraph_building_method=self.subgraph_building_method)

    def get_mcts_class(self, x, edge_index, node_idx: int = None, score_func: Callable = None):
        if self.explain_graph:
            node_idx = None
        else:
            assert node_idx is not None
        return MCTS(x, edge_index,
                    node_idx=node_idx,
                    score_func=score_func,
                    num_hops=self.num_hops,
                    n_rollout=self.rollout,
                    min_atoms=self.min_atoms,
                    c_puct=self.c_puct,
                    expand_atoms=self.expand_atoms,
                    high2low=self.high2low,
                    field=self.field)

    def visualization(self, explanation_results: list, prediction: Union[int, Tensor],
                      max_nodes: int, plot_utils: PlotUtils, words: Optional[list] = None,
                      y: Optional[Tensor] = None, vis_name: Optional[str] = None):
        if self.save:
            if vis_name is None:
                vis_name = f"{self.filename}.png"
        else:
            vis_name = None
        results = explanation_results[prediction]
        tree_node_x = find_closest_node_result(results, max_nodes=max_nodes)
        if self.explain_graph:
            if words is not None:
                plot_utils.plot(tree_node_x.ori_graph,
                                tree_node_x.coalition,
                                words=words,
                                figname=vis_name)
            else:
                plot_utils.plot(tree_node_x.ori_graph,
                                tree_node_x.coalition,
                                x=tree_node_x.data.x,
                                figname=vis_name)
        else:
            subset = self.mcts_state_map.subset
            subgraph_y = y[subset].to('cpu')
            subgraph_y = torch.tensor([subgraph_y[node].item()
                                       for node in tree_node_x.ori_graph.nodes()])
            plot_utils.plot(tree_node_x.ori_graph,
                            tree_node_x.coalition,
                            node_idx=self.mcts_state_map.node_idx,
                            y=subgraph_y,
                            figname=vis_name)

    def __call__(self, x: Tensor, edge_index: Tensor, **kwargs) \
            -> Tuple[None, List, List[Dict]]:
        r""" explain the GNN behavior for the graph using SubgraphX method

        Args:
            x (:obj:`torch.Tensor`): Node feature matrix with shape
              :obj:`[num_nodes, dim_node_feature]`
            edge_index (:obj:`torch.Tensor`): Graph connectivity in COO format
              with shape :obj:`[2, num_edges]`
            kwargs(:obj:`Dict`):
              The additional parameters
                - node_idx (:obj:`int`, :obj:`None`): The target node index when explain node classification task
                - max_nodes (:obj:`int`, :obj:`None`): The number of nodes in the final explanation results

        :rtype: (:obj:`None`, List[torch.Tensor], List[Dict])
        """
        max_nodes = kwargs.get('max_nodes')
        max_nodes = 14 if max_nodes is None else max_nodes  # default max subgraph size

        # 第一次原图的预测结果,并对结果进行格式化
        logits = self.model(x, edge_index)
        probs = F.softmax(logits, dim=1)
        probs = probs.squeeze()

        # 每种标签（Gas消耗）的所有解释结果子图
        explanation_results = []
        # 每种标签的最好解释结果评分标准，沙普利值和稀疏度
        related_preds = []

        ex_labels = probs.topk(self.explain_target_top_K, -1)  # 模型预测结果标签（所有的Gas消耗）

        for prediction in ex_labels[1]:  # （50个预测标签，那么少，预测标签是否等于我的Gas消耗，那是不是说明我的Gas历史消耗样本只有50种呢？？？）
            value_func = GnnNetsGC2valueFunc(self.model, target_class=prediction)  # 输出模型预测label的softmax分数函数
            payoff_func = self.get_reward_func(value_func) # 这个的意义何在 # payoff??
            self.mcts_state_map = self.get_mcts_class(x, edge_index, score_func=payoff_func)
            results = self.mcts_state_map.mcts(verbose=True)

            # l sharply score (可以起到特征权重测度的作用) （也就是我要预测的值的一个权重） （反映出每一个样本中的特征的影响力） （那我需要这个（权重）有什么用呢）
            # 夏普里值来源于合作博弈理论，是一种基于贡献的分配方式（为什么要使用sharply score?）
            data = Data(x=x, edge_index=edge_index)
            tree_node_x = find_closest_node_result(results, max_nodes=max_nodes)
            masked_node_list = [node for node in range(tree_node_x.data.x.shape[0])
                                if node in tree_node_x.coalition]
            maskout_node_list = [node for node in range(tree_node_x.data.x.shape[0]) # mask以外的标签（求这个有什么用呢？？）
                                 if node not in tree_node_x.coalition]
            masked_score = gnn_score(masked_node_list, data, value_func,
                                     subgraph_building_method='zero_filling')
            maskout_score = gnn_score(maskout_node_list, data, value_func,
                                      subgraph_building_method='zero_filling')
            sparsity_score = 1 - len(tree_node_x.coalition) / tree_node_x.ori_graph.number_of_nodes() # 这个的结果有什么用

            explanation_results.append(results)
            related_preds.append({'maskout': maskout_score,
                                  'masked': masked_score,
                                  'origin': probs[prediction],
                                  'sparsity': sparsity_score})
        return None, explanation_results, related_preds
