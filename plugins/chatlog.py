import twx
from telex.DatabaseMixin import DatabaseMixin, DbType
from telex.utils.decorators import group_only
from functools import partial
from telex import plugin


class ChatLogPlugin(plugin.TelexPlugin, DatabaseMixin):
    """
    Tracks a chat log and provides statistics and queries
    """
    HISTORY_QUERY_SIZE = 1000

    patterns = {
        "^{prefix}stats$": "stats_count",
        "^{prefix}stats_pattern (.*)": "stats_pattern",
        "^{prefix}loadhistory$": "load_history",
        "^{prefix}seen (([0-9]+)|@(.*)|(.*))": "seen",
        "^{prefix}stats_recent ?([\d]*?)$": "stats_count_recent",
        "^{prefix}stats_regex (.*)": "stats_regex",
    }

    usage = [
        "{prefix}stats: return chat stats",
        "{prefix}stats_pattern %somepattern%: returns stats filtered by SQL LIKE style pattern",
        "{prefix}seen (uid|@username|full name): Find the last time someone said something in the current chat",
        "{prefix}loadhistory: (Admin) load chatlog database from telegram history.",
        "{prefix}stats_recent (num_of_days): Stats for the only the last n days.",
        "{prefix}stats_regex pattern: Returns stats filtered by python style regex (case insensitive)",
    ]

    schema = {
        'msg_id': DbType.Integer,
        'timestamp': DbType.DateTime,
        'uid': DbType.Integer,
        'chat_id': DbType.Integer,
        'username': DbType.String,
        'full_name': DbType.String,
        'message': DbType.String,
    }
    primary_key = 'msg_id'

    def __init__(self):
        super().__init__()
        DatabaseMixin.__init__(self)

    def pre_process(self, msg):
        if not hasattr(msg, 'text'): #TODO support media
            return
        if hasattr(msg.src, 'username'):
            username = msg.src.username
        else:
            username = ""
        self.insert(msg_id=msg.id, timestamp=msg.date,
                    uid=msg.src.id, username=username,
                    full_name="{0} {1}".format(msg.src.first_name, msg.src.last_name or ''),
                    chat_id=abs(msg.dest.id), message=msg.text)

    @group_only
    def seen(self, msg, matches):
        chat_id = msg.dest.id
        if matches.group(2) is not None:
            return self.seen_by_id(chat_id, matches.group(2))
        elif matches.group(3) is not None:
            return self.seen_by_username(abs(chat_id), matches.group(3))
        else:
            return self.seen_by_fullname(abs(chat_id), matches.group(4))


    @group_only
    def load_history(self, msg, matches):
        chat = msg.dest
        msg_count = 0
        twx.get_history(chat, msg_count,
                        self.HISTORY_QUERY_SIZE,
                        partial(self.history_cb, msg_count, chat))

    def history_cb(self, msg_count, chat, success, msgs):
        if success:
            self.insert_history(msgs)
            msg_count += len(msgs)
            if len(msgs) == self.HISTORY_QUERY_SIZE:
                twx.get_history(chat, msg_count,
                                self.HISTORY_QUERY_SIZE,
                                partial(self.history_cb, msg_count, chat))
            else:
                twx.send_message(chat, "Loaded {0} messaged into the table".format(msg_count))

    def insert_history(self, msgs):
        # TODO Support Media Msgs
        values = [[msg.id, msg.date, msg.src.id, msg.src.username or '',
                   "{0} {1}".format(msg.src.first_name or '', msg.src.last_name or ''),
                   abs(msg.dest.id), msg.text] for msg in msgs if hasattr(msg, 'text') and None not in [msg.src, msg.dest]]
        columns = ['msg_id', 'timestamp', 'uid', 'username', 'full_name', 'chat_id', 'message']

        self.insert_many(columns, values)


    @group_only
    def stats_count_recent(self, msg, matches):
        if matches.group(1) is not None:
            return self.get_stats(abs(msg.dest.id), recent=matches.group(1))
        else:
            return self.get_stats(abs(msg.dest.id), recent=90)


    @group_only
    def stats_regex(self, msg, matches):
        return self.get_stats(abs(msg.dest.id), regex=matches.group(1))

    @group_only
    def stats_count(self, msg, matches):
        return self.get_stats(abs(msg.dest.id))

    @group_only
    def stats_pattern(self, msg, matches):
        return self.get_stats(abs(msg.dest.id), pattern=matches.group(1))

    def get_stats(self, chat_id, pattern=None, regex=None, recent=None):
        pattern_query = ""
        recent_query = ""
        if pattern is not None:
            pattern_query = " AND message LIKE ? "
        if regex is not None:
            pattern_query = " AND REGEXP(message, ?) "
            pattern = regex
        if recent is not None:
            recent_query = " AND timestamp > DATETIME('now', '-{} day') ".format(recent)

        query = """SELECT full_name, uid, COUNT(*) as count, ROUND(AVG(LENGTH(message)),2) as avglen FROM {0}
                   WHERE uid != {1} AND chat_id = {2} {3} {4} GROUP BY uid
                   ORDER BY count DESC""".format(self.table_name, self.bot.our_id, chat_id, pattern_query, recent_query)
        if(pattern is not None):
            results = self.query(query, parameters=(pattern,))
        else:
            results = self.query(query)

        if results is None or len(results) == 0:
           return "No stats match!"

        text = "Channel Chat Statistics (count) (avg len):\n"
        if recent is not None:
            text += "Recent Chat Only (last {} days)\n".format(recent)
        for result in results:
            text += "{name}: {count} ({avglen})\n".format(name=result["full_name"],
                                                          count=result["count"],
                                                          avglen=result["avglen"])
        return text


    def seen_by_username(self, chat_id, username):
        query = """SELECT * FROM {0}
                   WHERE username LIKE ? AND chat_id == {1}
                   ORDER BY timestamp DESC LIMIT 1 COLLATE NOCASE""".format(self.table_name, chat_id)

        results = self.query(query, parameters=(username,))

        return self.print_scene(results)

    def seen_by_fullname(self, chat_id, name):
        query = """SELECT * FROM {0}
                   WHERE full_name LIKE ? AND chat_id == {1}
                   ORDER BY timestamp DESC LIMIT 1 COLLATE NOCASE""".format(self.table_name, chat_id)

        results = self.query(query, parameters=(name,))

        return self.print_scene(results)

    def seen_by_id(self, chat_id, uid):
        query = """SELECT * FROM {0}
                   WHERE uid == ? AND chat_id == {1}
                   ORDER BY timestamp DESC LIMIT 1""".format(self.table_name, chat_id)

        results = self.query(query, parameters=(uid,))

        return self.print_scene(results)

    def print_scene(self, results):
        if len(results) == 0:
            return "Cannot find that user in the history"
        else:
            return "{full_name} last seen at {timestamp} saying:\n{msg}".format(full_name=results[0]["full_name"], timestamp=results[0]["timestamp"], msg=results[0]["message"])
