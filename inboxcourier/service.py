import base64
import email
import io
import pickle
import os
import schedule
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.readonly'
]


class Service:
    def __init__(self, creds_file, creds_dir):
        creds = None

        # The file token.pickle stores the user's access and refresh tokens,
        # and is created automatically when the authorization flow completes
        # for the first time.
        token_path = '{}/token.pickle'.format(creds_dir)
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_path = '{}/{}'.format(creds_dir, creds_file)
                flow = InstalledAppFlow.from_client_secrets_file(
                    creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        self.authorized_session = build('gmail', 'v1', credentials=creds)

    def watch_inbox(self, pubsub_request):
        schedule.every().day.do(
            self._watch_inbox_helper,
            request=pubsub_request)

        schedule.run_all()
        while True:
            schedule.run_pending()
            time.sleep(1)

    def _watch_inbox_helper(self, request):
        self.authorized_session.users().watch(
            userId='me',
            body=request
        ).execute()

        print('[debug] Inbox watch initiated. request: {}'.format(request))

    def check_inbox(self, query_string, has_attachments, max_messages):
        try:
            message_list = self._list_messages(query_string, max_messages)
            messages = []
            for message_id in message_list:
                message_data = self._get_message(message_id['id'])

                contents = self._get_message_contents(has_attachments, message_data)
                messages.append(contents)
                self._process_message(message_id['id'])
            return messages
        except Exception as error:
            # logger.error('Cannot get mail: %s' % error)
            print('check_inbox error: {}'.format(error))

    def _list_messages(self, query_string, max_messages):
        """List all Messages of the user's mailbox matching the query.

        Args:
            service: Authorized Gmail API service instance.
            query: String used to filter messages returned.
            Eg.- 'from:user@some_domain.com' for Messages from a
            particular sender.

        Returns:
            List of Messages that match the criteria of the query. Note that
            the returned list contains Message IDs, you must use get with the
            appropriate ID to get the details of a Message.
        """
        try:
            if max_messages:
                response = self.authorized_session.users().messages().list(
                    userId='me',
                    maxResults=max_messages,
                    q=query_string
                ).execute()
            else:
                response = self.authorized_session.users().messages().list(
                    userId='me',
                    q=query_string).execute()

            messages = []
            if 'messages' in response:
                messages.extend(response['messages'])

            while 'nextPageToken' in response and max_messages and len(messages) < max_messages:
                # Unused for some reason, TODO: use it
                # page_token = response['nextPageToken']
                if max_messages:
                    response = self.authorized_session.users().messages().list(
                        userId='me',
                        maxResults=max_messages,
                        q=query_string
                    ).execute()
                else:
                    response = self.authorized_session.users().messages().list(
                        userId='me',
                        q=query_string
                    ).execute()
                if 'messages' in response:
                    messages.extend(response['messages'])
            return messages
        except Exception as error:
            # logger.error('Cannot get emails matching this query: %s' % error)
            print('no emails matching this query: {}'.format(error))

    def _get_message(self, msg_id):
        """Get a Message with given ID.

        Args:
            service: Authorized Gmail API service instance.
            msg_id: The ID of the Message required.

        Returns:
            A Message.
        """
        try:
            message = self.authorized_session.users().messages().get(
                userId='me',
                id=msg_id,
                format='raw'
            ).execute()

            message = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
            return message
        except HttpError as error:
            # logger.error('Cannot get email with id %s: %s' % (msg_id, error))
            print('no emails with id {}: {}'.format(msg_id, error))

    def _get_message_contents(self, has_attachments, message):
        if has_attachments:
            return {
                'attachment': self._get_attachments(message),
                'filename': self._get_filename(message)
            }
        else:
            return self._get_body(message)

    def _get_body(self, message):
        """Get body of a Message."""
        try:
            message_body = ''
            msg = email.message_from_bytes(message)
            for part in msg.walk():
                if part.get_content_maintype() == 'text':
                    message_body += part.get_payload()
            return message_body
        except Exception as error:
            # logger.error('Cannot get email body: %s' % error)
            print('error retrieving email body: {}'.format(error))

    def _get_attachments(self, message):
        """Extracts PDF from email.

        Returns:
            Attachment in a ByteIO object.
        """
        try:
            msg = email.message_from_bytes(message)
            raw_attachment = io.BytesIO()
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue
                fileName = part.get_filename()
                if fileName:
                    raw_attachment.write(part.get_payload(decode=True))
            return raw_attachment
        except Exception as error:
            # logger.error('Cannot get PDF from email: %s' % error)
            print('error parsing attachment: {}'.format(error))

    def get_filename(self, message):
        """Extracts filename from email."""
        try:
            msg = email.message_from_bytes(message)
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue
                fileName = part.get_filename()
                if fileName:
                    return fileName
        except Exception as error:
            # logger.error('Cannot get PDF name: %s' % error)
            print('error retrieving filename: {}'.format(error))

    def _process_message(self, msg_id):
        """Mark processed emails as unread.

        Args:
            service: Authorized Gmail API service instance.
            msg_id: The id of the message required.
        """
        try:
            label_object = self._create_message_labels()
            self._remove_unread_label(label_object)
            self._modify_message(msg_id, label_object)
        except HttpError as error:
            # logger.error('Cannot mark email as unread: %s' % error)
            print('error marking email as unread: {}'.format(error))

    def _create_message_labels(self):
        """Create object to update labels.

        Returns:
            A label update object.
        """
        return {'removeLabelIds': [], 'addLabelIds': []}

    def _remove_unread_label(self, label_object):
        """Modify label update object to remove the UNREAD label.

        Returns:
            A label update object.
        """
        label_object['removeLabelIds'].append('UNREAD')
        return label_object

    def _modify_message(self, msg_id, msg_labels):
        """Modify the Labels on the given Message.

        Args:
            service: Authorized Gmail API service instance.
            msg_id: The id of the message required.
            msg_labels: The change in labels.

        Returns:
            Modified message, containing updated labelIds, id and threadId.
        """
        try:
            message = self.authorized_session.users().messages().modify(
                userId='me',
                id=msg_id,
                body=msg_labels
            ).execute()

            return message
        except HttpError as error:
            # logger.error(error)
            print('error modifying message label: '.format(error))
