# -- coding: gbk --
"""
How Powerful are Graph Neural Networks
https://arxiv.org/abs/1810.00826
https://openreview.net/forum?id=ryGs6iA5Km
Author's implementation: https://github.com/weihua916/powerful-gnns
"""
from typing import Any
from torch_geometric.data.batch import Batch
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn.conv import GINConv, GATv2Conv
from torch_geometric.nn.glob import global_add_pool, global_mean_pool, global_max_pool, global_sort_pool


class ApplyNodeFunc(nn.Module):
    """Update the node feature hv with MLP, BN and ReLU."""

    def __init__(self, mlp):
        super(ApplyNodeFunc, self).__init__()
        self.mlp = mlp
        self.bn = nn.BatchNorm1d(self.mlp.output_dim)

    def forward(self, h):
        h = self.mlp(h)
        h = self.bn(h)
        h = F.relu(h)
        return h


class MLP(nn.Module):
    """MLP with linear output"""

    def __init__(self, num_layers, input_dim, hidden_dim, output_dim):
        """MLP layers construction
        Paramters
        ---------
        num_layers: int
            The number of linear layers
        input_dim: int
            The dimensionality of input features
        hidden_dim: int
            The dimensionality of hidden units at ALL layers
        output_dim: int
            The number of classes for prediction
        """
        super(MLP, self).__init__()
        self.linear_or_not = True  # default is linear model
        self.num_layers = num_layers
        self.output_dim = output_dim

        if num_layers < 1:
            raise ValueError("number of layers should be positive!")
        elif num_layers == 1:
            # Linear model
            self.linear = nn.Linear(input_dim, output_dim)
        else:
            # Multi-layer model
            self.linear_or_not = False
            self.linears = torch.nn.ModuleList()
            self.batch_norms = torch.nn.ModuleList()

            self.linears.append(nn.Linear(input_dim, hidden_dim))
            for layer in range(num_layers - 2):
                self.linears.append(nn.Linear(hidden_dim, hidden_dim))
            self.linears.append(nn.Linear(hidden_dim, output_dim))

            for layer in range(num_layers - 1):
                self.batch_norms.append(nn.BatchNorm1d(hidden_dim))

    def forward(self, x):
        if self.linear_or_not:
            # If linear model
            return self.linear(x)
        else:
            # If MLP
            h = x
            for i in range(self.num_layers - 1):
                h = F.relu(self.batch_norms[i](self.linears[i](h)))
            return self.linears[-1](h)


def arguments_read(*args, **kwargs):
    data: Batch = kwargs.get('data') or None
    if not data:
        if not args:
            assert 'x' in kwargs
            assert 'edge_index' in kwargs
            x, edge_index = kwargs['x'], kwargs['edge_index'],
            batch = kwargs.get('batch')
            if batch is None:
                batch = torch.zeros(kwargs['x'].shape[0], dtype=torch.int64, device=x.device)
        elif len(args) == 2:
            x, edge_index = args[0], args[1]
            batch = torch.zeros(args[0].shape[0], dtype=torch.int64, device=x.device)
        elif len(args) == 3:
            x, edge_index, batch = args[0], args[1], args[2]
        else:
            raise ValueError(f"forward's args should take 2 or 3 arguments but got {len(args)}")
    else:
        x, edge_index, batch = data.x, data.edge_index, data.batch
    return x, edge_index, batch


class GIN(nn.Module):
    """GIN model"""

    def __init__(self, num_layers, num_mlp_layers, input_dim, hidden_dim,
                 output_dim, graph_pooling_type, neighbor_pooling_type,
                 learn_eps=False, final_dropout=0.2, alpha=0.02, explain=False,
                 use_attention=True):
        """
        model parameters setting
        Paramters
        ---------
        num_layers: int
            The number of linear layers in the neural network
        num_mlp_layers: int
            The number of linear layers in mlps
        input_dim: int
            The dimensionality of input features
        hidden_dim: int
            The dimensionality of hidden units at ALL layers
        output_dim: int
            The number of classes for prediction
        final_dropout: float
            dropout ratio on the final linear layer
        learn_eps: boolean
            If True, learn epsilon to distinguish center nodes from neighbors
            If False, aggregate neighbors and center nodes altogether.
        neighbor_pooling_type: str
            how to aggregate neighbors (sum, mean, or max)
        graph_pooling_type: str
            how to aggregate entire nodes in a graph (sum, mean or max)
        """
        super(GIN, self).__init__()
        self.num_layers = num_layers
        self.learn_eps = learn_eps
        self.leakyrelu = nn.LeakyReLU(alpha)
        self.explain = explain

        # set attention
        self.use_attention = use_attention
        if use_attention:
            self.attention_layers = torch.nn.ModuleList()
            for layer in range(self.num_layers - 1):
                self.attention_layers.append(GATv2Conv(hidden_dim, hidden_dim,
                                                       heads=3, add_self_loops=False, concat=False))

        # List of MLPs
        self.gin_layers = torch.nn.ModuleList()
        self.batch_norms = torch.nn.ModuleList()

        for layer in range(self.num_layers - 1):
            if layer == 0:
                mlp = MLP(num_mlp_layers, input_dim, hidden_dim, hidden_dim)
            else:
                mlp = MLP(num_mlp_layers, hidden_dim, hidden_dim, hidden_dim)
            self.gin_layers.append(GINConv(ApplyNodeFunc(mlp), eps=self.learn_eps, aggr=neighbor_pooling_type))
            self.batch_norms.append(nn.BatchNorm1d(hidden_dim))

        # Linear function for graph poolings of output of each layer
        # which maps the output of different layers into a prediction score
        self.linears_prediction = torch.nn.ModuleList()
        for layer in range(num_layers):
            if layer == 0:
                self.linears_prediction.append(
                    nn.Linear(input_dim, output_dim))
            else:
                self.linears_prediction.append(
                    nn.Linear(hidden_dim, output_dim))
        self.drop = nn.Dropout(final_dropout)

        # 设置图读出策略
        if graph_pooling_type == 'sum':
            self.pool = global_add_pool
        elif graph_pooling_type == 'mean':
            self.pool = global_mean_pool
        elif graph_pooling_type == 'max':
            self.pool = global_max_pool
        else:
            raise NotImplementedError

    def forward(self, *args, **kwargs) -> torch.Tensor:
        h, edge_index, batch = arguments_read(*args, **kwargs)

        # list of hidden representation at each layer (including input)
        hidden_rep = [h]

        for i in range(self.num_layers - 1):
            h = self.gin_layers[i](h, edge_index)
            h = self.batch_norms[i](h)
            h = self.leakyrelu(h)
            if self.use_attention:
                hidden_rep.append(self.attention_layers[i](h, edge_index))
            else:
                hidden_rep.append(h)

        score_over_layer = 0
        # perform pooling over all nodes in each graph in every layer
        for i, h in enumerate(hidden_rep):
            pooled_h = self.pool(h, batch)
            score_over_layer += self.drop(self.linears_prediction[i](pooled_h))
        # 此处需要softmax
        # 当模型需要进行解释时不进行log_softmax
        if self.explain:
            return score_over_layer
        else:
            return torch.log_softmax(score_over_layer, dim=1)
