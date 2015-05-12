import tgl
import logging
import re
from TelegramPluginManager import TelegramPluginManager

#logging.basicConfig(level=logging.DEBUG)



class TelegramBot:
    our_id = 0
    binlog_done = False

    def __init__(self):
        self.plugin_manager = TelegramPluginManager(self)
        self.load_plugins()

    def load_plugins(self):
        # Tell it the default place(s) where to find plugins
        self.plugin_manager.setPluginPlaces(["./plugins/"])
        # Load all plugins
        self.plugin_manager.collectPlugins()

        # Activate all loaded plugins
        for plugin_info in self.plugin_manager.getAllPlugins():
            plugin_info.bot = self
            self.plugin_manager.activatePluginByName(plugin_info.name)

    # Callbacks
    def on_binlog_replay_end(self):
        self.binlog_done = True

    def on_get_difference_end(self):
        pass

    def on_our_id(self, current_id):
        self.our_id = current_id
        return "Set ID: " + str(self.our_id)

    def on_msg_receive(self, msg):
        if msg["out"] and not self.binlog_done:
            return

        if msg["to"]["id"] == self.our_id:  # direct message
            ptype = msg["from"]["type"]
            pid = msg["from"]["id"]
        else:  # chat room
            ptype = msg["to"]["type"]
            pid = msg["to"]["id"]

        for plugin_info in self.plugin_manager.getAllPlugins():
            for pattern in plugin_info.plugin_object.patterns:
                if plugin_info.plugin_object.is_activated:
                    matches = re.search(pattern, msg["text"])
                    if matches is not None:
                        reply = plugin_info.plugin_object.run(msg["text"], matches)

                        if reply is not None:
                            send_msg(ptype, pid, reply)

    def on_secret_chat_update(self, peer, types):
        return "on_secret_chat_update"

    def on_user_update(self):
        pass

    def on_chat_update(self):
        pass


def send_msg(ptype, pid, msg):
    tgl.send_msg(ptype, pid, msg)

# test driver without tg running
if __name__ == "__main__":
    bot = TelegramBot()

    # Set callbacks
    tgl.set_on_binlog_replay_end(bot.on_binlog_replay_end)
    tgl.set_on_get_difference_end(bot.on_get_difference_end)
    tgl.set_on_our_id(bot.on_our_id)
    tgl.set_on_msg_receive(bot.on_msg_receive)
    tgl.set_on_secret_chat_update(bot.on_secret_chat_update)
    tgl.set_on_user_update(bot.on_user_update)
    tgl.set_on_chat_update(bot.on_chat_update)

    bot.on_binlog_replay_end()
    bot.on_our_id(999)

    message = dict()
    message["from"] = dict()
    message["from"]["id"] = 222
    message["from"]["type"] = 1
    message["to"] = dict()
    message["to"]["id"] = 333
    message["to"]["type"] = 1
    message["out"] = False
    message["text"] = "!btc USD 55"

    bot.on_msg_receive(message)