import json
import logging

import requests

gephi_master_url = 'http://localhost:8080/workspace0?operation=updateGraph'

log = logging.getLogger("gephi")

class GephiStreamer(object):
    def __init__(self):
    
        self.nodes = {}
        self.edges = {}

    def __send(self, data):
        to_send = json.dumps(data)
        try:
            requests.post(gephi_master_url, data=to_send)
        except IOError as e:
            log.error('can not connect to gephi')

    def add_node(self, node_data, id_key="id", label_key="screen_name"):
        """
        Must be object with sn_id and name properties
        :param node_data:
        :return:
        """
        if node_data.sn_id not in self.nodes:
            self.__send({'an': {
                node_data[id_key]: dict({'label': node_data[label_key]}, **node_data)}})
        elif self.nodes[node_data[id_key]] is None:
            self.__send({'cn': {
                node_data[id_key]: dict({'label': node_data[label_key]}, **node_data)}})
        self.nodes[node_data.sn_id] = node_data

    def add_relation(self, from_node_id, to_node_id, relation_type):
        """
        sending to gephi master graph streamer two nodes and one edge
        :param from_node: {identifier:{'label':..., 'weight':...}}
        :param to_node: {identifier:{'label':..., 'weight':...}}
        :return:
        """
        if from_node_id not in self.nodes:
            self.__send({'an': {from_node_id: {'label': from_node_id, 'not_loaded': True}}})
            self.nodes[from_node_id] = None
        if to_node_id not in self.nodes:
            self.__send({'an': {to_node_id: {'label': to_node_id, 'not_loaded': True}}})
            self.nodes[to_node_id] = None

        edge_id = "%s_%s" % (from_node_id, to_node_id)
        saved = self.edges.get(edge_id)
        if saved is None:
            self.edges[edge_id] = 1
            self.__send(
                {'ae': {
                    edge_id: {'source': from_node_id,
                              'target': to_node_id,
                              'directed': True,
                              'weight': self.edges[edge_id],
                              'label': relation_type
                              }
                }})
        else:
            saved += 1
            self.edges[edge_id] = saved
            self.__send({'ce': {edge_id: {'weight': saved}}})

