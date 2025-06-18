
TODO:
这是一个计算流体网络中管道流速的python项目

用户输入元件与管道链接关系 软件输出每个管道的流速

有以下几种元件 

管道:
链接不同的元件
管道的输入流速等于管道的输出流速

入口:
提供流体

出口:
消耗流体

分流器:
最多 1输入 3输出
输入流量等于输出流量 元件本身有最大流量限制
总输出口的流量等于总输入口的流量
优先平均分配输出 如果某个管道已经满了 就在剩余的管道中优先平均分配输出
如果所有管道都满了还是没有输出完 就降低整个元件的流量 反压输入口

汇流器:
最多 3输入 1输出
输入流量等于输出流量 元件本身有最大流量限制
总输出口的流量等于总输入口的流量
优先平均分配输入 如果某个管道已经空了 就在剩余管道中优先平均分配输入
如果所有管道都空了 就降低整个元件的流量

限流器:
最多 1输入 1输出
输入流量等于输出流量 元件本身有最大流量限制



计算flow:
flow = sum(i.supply for i in inputs)
flow = min(self.max_flow, flow)

计算capacity:
flow = self.max_flow
s = [i.supply for i in self.inputs]
for i in self.inputs:
  i.capacity = 0

e = min(i.supply for i in s)
f = min(e*len(s), flow)
flow -= f
for i in still_in_s(self.inputs):
  i.capacity += f/len(s)

s[:] -= f/len(s)
# pop all 0 value element in s[]
# loop until len(s) == 0 or flow == 0


计算supply:
flow = current_flow
c = [i.capacity for i in self.outputs]
for i in self.outputs:
  i.supply = 0

e = min(i.capacity for i in c)
f = min(e*len[c], flow)
flow -= f
for i in still_in_c(self.outputs):
  i.supply += f/len(c)

c[:] -= f/len(c)
# pop all 0 value element in c[]
# loop until len(c) == 0 or flow == 0 