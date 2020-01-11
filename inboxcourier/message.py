import base64
import email
import io

from googleapiclient.errors import HttpError


class AttachmentPart:
    def __init__(self, filename, data):
        self.filename = filename
        self.data = data

    def load(self):
        return {
            'filename': self.filename,
            'data': self.data
        }


class Payload:
    def __init__(self):
        self.sender = None
        self.cc = None
        self.bcc = None
        self.subject = None
        self.text_body = None
        self.html_body = None
        self.attachments = []

    def deliver(self):
        payload = dict()
        if self.sender:
            payload['from'] = self.sender
        if self.cc:
            payload['cc'] = self.cc
        if self.bcc:
            payload['bcc'] = self.bcc
        if self.subject:
            payload['subject'] = self.subject
        if self.text_body:
            payload['text_body'] = self.text_body
        if self.html_body:
            payload['html_body'] = self.html_body
        if len(self.attachments) != 0:
            attachments = [att.load() for att in self.attachments]
            payload['attachments'] = attachments
        return payload

    def add_sender(self, sender):
        self.sender = sender

    def add_cc(self, cc_list):
        if isinstance(cc_list, list):
            self.cc = cc_list
        else:
            raise TypeError('input must be a list')

    def add_bcc(self, bcc_list):
        if isinstance(bcc_list, list):
            self.bcc = bcc_list
        else:
            raise TypeError('input must be a list')

    def add_subject(self, subject):
        self.subject = subject

    def add_text_body(self, text_body):
        self.text_body = text_body

    def add_html_body(self, html_body):
        self.html_body = html_body

    def add_attachment(self, attachment):
        if isinstance(attachment, AttachmentPart):
            self.attachments.append(attachment)
        else:
            raise TypeError('input must be an AttachmentPart')


class MessageHandler:
    def __init__(self):
        self.payload = Payload()

    def process_messages(self, messages, has_attachments):
        try:
            for message_id in messages:
                raw_message = self._get_raw_message(message_id['id'])
                self._parse_message_contents(has_attachments, raw_message)
                self._mark_as_read(message_id['id'])
            return self.payload.deliver()
        except Exception as error:
            # logger.error('Cannot get mail: %s' % error)
            print('check_inbox error: {}'.format(error))

    def _get_raw_message(self, msg_id):
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=msg_id,
                format='raw'
            ).execute()

            message = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
            return message
        except HttpError as error:
            # logger.error('Cannot get email with id %s: %s' % (msg_id, error))
            print('no emails with id {}: {}'.format(msg_id, error))

    def _parse_message_contents(self, has_attachments, message):
        self._get_body(message)
        if has_attachments:
            self._get_attachments()

    def _get_body(self, message):
        """Get body of a Message."""
        try:
            text_body = ''
            has_text_body = False

            msg = email.message_from_bytes(message)
            for part in msg.walk():
                if part.get_content_maintype() == 'text':
                    has_text_body = True
                    text_body += part.get_payload()
            if has_text_body:
                self.payload.add_text_body(text_body)

            html_body = ''
            has_html_body = False

            msg = email.message_from_bytes(message)
            for part in msg.walk():
                if part.get_content_maintype() == 'html':
                    has_html_body = True
                    html_body += part.get_payload()
            if has_html_body:
                self.payload.add_html_body(html_body)

        except Exception as error:
            # logger.error('Cannot get email body: %s' % error)
            print('error retrieving email body: {}'.format(error))

    def _get_attachments(self, message):
        try:
            parsed_message = email.message_from_bytes(message)
            raw_attachment = io.BytesIO()

            for part in parsed_message.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue

                filename = part.get_filename()
                if filename:
                    data = raw_attachment.write(part.get_payload(decode=True))
                    self.payload.add_attachment(AttachmentPart(filename, data))

        except Exception as error:
            # logger.error('Cannot get PDF from email: %s' % error)
            print('error parsing attachment: {}'.format(error))

    def _mark_as_read(self, msg_id):
        try:
            labels = {'removeLabelIds': ['UNREAD'], 'addLabelIds': []}
            self.authorized_session.users().messages().modify(
                userId='me',
                id=msg_id,
                body=labels).execute()
        except HttpError as error:
            # logger.error('Cannot mark email as unread: %s' % error)
            print('error marking email as unread: {}'.format(error))
