# -*- coding: utf-8 -*-
# Copyright 2017 Dunbar Security Solutions, Inc.
#
# This file is part of Cyphon Engine.
#
# Cyphon Engine is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Cyphon Engine is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Cyphon Engine. If not, see <http://www.gnu.org/licenses/>.
"""
Tests Alert views.
"""

# standard library
from smtplib import SMTPAuthenticationError
try:
    from unittest.mock import Mock, patch
except ImportError:
    from mock import Mock, patch

# third party
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import TestCase, TransactionTestCase
from testfixtures import LogCapture

# local
from appusers.models import AppUser
from alerts.models import Alert, Analysis, Comment
from alerts.signals import tag_alert, tag_analysis, tag_comment
from tags.models import TagRelation
from tests.fixture_manager import get_fixtures


class SendCommentNotificationTestCase(TestCase):
    """
    Tests the send_comment_notification receiver.
    """
    fixtures = get_fixtures(['comments'])

    def setUp(self):
        self.comment = Comment.objects.get(pk=1)

    def test_old_alert(self):
        """
        Tests that the send_comment_notification receiver doesn't
        send an email when an existing alert is updated.
        """
        with patch('alerts.signals.emails_enabled', return_value=True):
            with patch('alerts.signals.compose_comment_email') as mock_compose:
                comment = Comment.objects.get(pk=1)
                comment.save()
                mock_compose.assert_not_called()

    def test_new_alert_emails_enabled(self):
        """
        Tests that the send_comment_notification receiver doesn't
        send an email when a new alert is updated and email notifcations
        are enabled.
        """
        mock_email = Mock()
        with patch('alerts.signals.emails_enabled', return_value=True):
            with patch('alerts.signals.compose_comment_email',
                       return_value=mock_email) as mock_compose:
                comment = Comment.objects.get(pk=1)
                user = AppUser.objects.get(pk=2)
                comment.pk = None
                comment.save()
                mock_compose.assert_called_with(comment, user)
                self.assertEqual(mock_compose.call_count, 1)
                self.assertEqual(mock_email.send.call_count, 1)

    def test_new_alert_emails_disabled(self):
        """
        Tests that the send_comment_notification receiver doesn't
        send an email when a new alert is updated and email notifcations
        are disabled.
        """
        mock_email = Mock()
        with patch('alerts.signals.emails_enabled', return_value=False):
            with patch('alerts.signals.compose_comment_email',
                       return_value=mock_email) as mock_compose:
                comment = Comment.objects.get(pk=1)
                comment.pk = None
                comment.save()
                mock_compose.assert_not_called()

    def test_email_error(self):
        """
        Tests that an error message is logged when an
        SMTPAuthenticationErro is encountered.
        """
        mock_email = Mock()
        mock_email.send = Mock(
            side_effect=SMTPAuthenticationError(535, 'foobar'))
        with patch('alerts.signals.emails_enabled', return_value=True):
            with patch('alerts.signals.compose_comment_email',
                       return_value=mock_email):
                with LogCapture() as log_capture:
                    comment = Comment.objects.get(pk=1)
                    comment.pk = None
                    comment.save()
                    log_capture.check(
                        ('alerts.signals',
                         'ERROR',
                         'An error occurred when sending an email '
                         'notification: (535, \'foobar\')'),
                    )


class TagAlertTestCase(TransactionTestCase):
    """
    Tests the tag_alert receiver.
    """
    fixtures = get_fixtures(['alerts', 'datataggers'])

    def setUp(self):
        super(TagAlertTestCase, self).setUp()
        post_save.connect(tag_alert, sender=Alert)
        self.alert = Alert.objects.get(pk=2)

    def tearDown(self):
        super(TagAlertTestCase, self).tearDown()
        post_save.disconnect(tag_alert, sender=Alert)

    def test_old_alert(self):
        """
        Tests that an old Alert is not tagged.
        """
        self.alert.save()
        self.assertEquals(len(self.alert.associated_tags), 0)

    def test_new_alert(self):
        """
        Tests that a new Alert is tagged.
        """
        alert = self.alert
        alert.pk = None
        alert.save()
        self.assertEquals(len(alert.associated_tags), 2)


class TagAnalysisTestCase(TransactionTestCase):
    """
    Tests the tag_comment receiver.
    """
    fixtures = get_fixtures(['alerts', 'tags'])

    def setUp(self):
        super(TagAnalysisTestCase, self).setUp()
        post_save.connect(tag_analysis, sender=Analysis)

    def tearDown(self):
        super(TagAnalysisTestCase, self).tearDown()
        post_save.disconnect(tag_analysis, sender=Analysis)

    def test_tag_analysis(self):
        """
        Tests that a Comment is tagged when saved.
        """
        analysis = Analysis.objects.get(pk=3)
        analysis_type = ContentType.objects.get_for_model(Analysis)
        tag_relations = TagRelation.objects.filter(content_type=analysis_type,
                                                   object_id=analysis.pk)
        self.assertEquals(tag_relations.count(), 1)
        analysis.notes = 'I like cats and dogs.'
        analysis.save()
        tag_relations = TagRelation.objects.filter(content_type=analysis_type,
                                                   object_id=analysis.pk)
        self.assertEquals(tag_relations.count(), 3)


class TagCommentTestCase(TransactionTestCase):
    """
    Tests the tag_comment receiver.
    """
    fixtures = get_fixtures(['comments', 'tags'])

    def setUp(self):
        super(TagCommentTestCase, self).setUp()
        post_save.connect(tag_comment, sender=Comment)

    def tearDown(self):
        super(TagCommentTestCase, self).tearDown()
        post_save.disconnect(tag_comment, sender=Comment)

    def test_tag_comment(self):
        """
        Tests that a Comment is tagged when saved.
        """
        comment = Comment.objects.get(pk=3)
        comment_type = ContentType.objects.get_for_model(Comment)
        tag_relations = TagRelation.objects.filter(content_type=comment_type,
                                                   object_id=comment.pk)
        self.assertEquals(tag_relations.count(), 0)

        comment.content = 'I like cats and dogs.'
        comment.save()
        tag_relations = TagRelation.objects.filter(content_type=comment_type,
                                                   object_id=comment.pk)
        self.assertEquals(tag_relations.count(), 2)
