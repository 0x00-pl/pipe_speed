"""管道网络元件数据模型"""

from dataclasses import dataclass, field


@dataclass
class Pipe:
    """管道（图的边）：连接两个元件的流体通道"""
    source: str            # 上游节点名
    target: str            # 下游节点名
    supply: float = 0.0    # 上游元件想推的量（正向传播设置）
    capacity: float = float('inf')  # 下游元件能接的量（反向传播设置）
    max_flow: float = 120.0  # 管道自身容量上限

    @property
    def flow(self) -> float:
        """实际流速 = min(supply, capacity)"""
        return min(self.supply, self.capacity)


@dataclass
class Inlet:
    """入口：提供流体，0 入边，≥1 出边"""
    name: str
    max_flow: float = 120.0  # 最大供流速率（可能因下游阻塞而降低）


@dataclass
class Outlet:
    """出口：消耗流体，≥1 入边，0 出边"""
    name: str
    max_flow: float = 120.0  # 最大消耗速率


@dataclass
class Splitter:
    """分流器：1 入边，1~3 出边，均分输入到输出"""
    name: str
    max_flow: float = 120.0  # 元件最大吞吐量


@dataclass
class Merger:
    """汇流器：1~3 入边，1 出边，合并多路输入"""
    name: str
    max_flow: float = 120.0  # 元件最大吞吐量


@dataclass
class Limiter:
    """限流器：1 入边，1 出边，限制通过流量"""
    name: str
    max_flow: float = 120.0  # 元件最大吞吐量
