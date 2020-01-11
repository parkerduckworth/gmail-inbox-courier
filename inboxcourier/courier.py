import threading

from service import Service


class Courier:
    def __init__(self, creds_file, creds_dir='.'):
        self.service = Service(creds_file, creds_dir)

    def run(self, label_ids, filter_action, topic_name):
        # TODO: validate input
        pubsub_request = {
            'labelIds': label_ids,
            'labelFilterAction': filter_action,
            'topicName': topic_name
        }

        watcher_thread = threading.Thread(
            target=self.service.watch_inbox,
            args=(pubsub_request,),
            daemon=True)

        watcher_thread.start()

    def deliver_mail(self, query_string, has_attachments, max_messages=None):
        return self.service.check_inbox(query_string, has_attachments, max_messages)
