from uuid import uuid4

from django.test import TestCase

from rest_framework.test import APIRequestFactory
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request

import pytest
import rest_framework

from utils.test_utils import BaseTestCase
from codecov_auth.tests.factories import SessionFactory, OwnerFactory
from codecov_auth.authentication import CodecovSessionAuthentication


# Using the standard RequestFactory API to create a form POST request

class TestAuthentication(BaseTestCase):

    def test_auth(self, db):
        a = "2|1:0|10:1557329312|15:bitbucket-token|48:OGY5YmM2Y2ItZmQxNC00M2JjLWJiYjUtYmUxZTdjOTQ4ZjM0|459669157b19d2e220f461e02c07c377a455bc532ad0c2b8b69b2648cfbe3914"
        session = SessionFactory.create(token="8f9bc6cb-fd14-43bc-bbb5-be1e7c948f34")
        request_factory = APIRequestFactory()
        request = request_factory.post('/notes/', {'title': 'new idea'}, HTTP_AUTHORIZATION=f'frontend {a}')
        authenticator = CodecovSessionAuthentication()
        result = authenticator.authenticate(request)
        assert result is not None
        user, token = result
        assert user == session.owner
        assert token == session

    def test_decode_token_from_cookie(self):
        val = "2|1:0|10:1557329312|15:bitbucket-token|48:OGY5YmM2Y2ItZmQxNC00M2JjLWJiYjUtYmUxZTdjOTQ4ZjM0|459669157b19d2e220f461e02c07c377a455bc532ad0c2b8b69b2648cfbe3914"
        expected_response = "8f9bc6cb-fd14-43bc-bbb5-be1e7c948f34"
        authenticator = CodecovSessionAuthentication()
        assert expected_response == authenticator.decode_token_from_cookie(val)

    def test_decode_token_bad_signature(self):
        val = "2|1:0|10:1557329312|15:bitbucket-token|48:OGY5YmM2Y2ItZmQxNC00M2JjLWJiYjUtYmUxZTdjOTQ4ZjM0|aaaaaaaa7baad2e220faaae02c07c377aaaabca32ad0c2b8baab2aa8cfbe3aaa"
        expected_response = "8f9bc6cb-fd14-43bc-bbb5-be1e7c948f34"
        authenticator = CodecovSessionAuthentication()
        with pytest.raises(rest_framework.exceptions.AuthenticationFailed):
            authenticator.decode_token_from_cookie(val)

    def test_auth_no_token(self, db):
        SessionFactory.create()
        token = uuid4()
        request_factory = APIRequestFactory()
        request = request_factory.post(
            '/notes/', {'title': 'new idea'}, HTTP_AUTHORIZATION=f'frontend {token}')
        authenticator = CodecovSessionAuthentication()
        with pytest.raises(rest_framework.exceptions.AuthenticationFailed):
            authenticator.authenticate(request)

class CodecovSessionAuthenticationImpersonationTests(TestCase):
    def setUp(self):
        token = "2|1:0|10:1557329312|15:bitbucket-token|48:OGY5YmM2Y2ItZmQxNC00M2JjLWJiYjUtYmUxZTdjOTQ4ZjM0|459669157b19d2e220f461e02c07c377a455bc532ad0c2b8b69b2648cfbe3914"
        self.session = SessionFactory(
            token="8f9bc6cb-fd14-43bc-bbb5-be1e7c948f34",
            owner=OwnerFactory(staff=True)
        )

        self.authorization_header = f'frontend {token}'
        self.user_to_impersonate = 'codecov'
        self.impersonated_user = OwnerFactory(username=self.user_to_impersonate)
        self.authenticator = CodecovSessionAuthentication()
        self.request_factory = APIRequestFactory()

    def _create_request(self, cookie='', service=''):
        self.request_factory.cookies["staff_user"] = cookie
        request = Request(self.request_factory.get(
            '',
            HTTP_AUTHORIZATION=self.authorization_header
        ))
        request.parser_context = {"kwargs": {"service": service or self.impersonated_user.service}}
        return request

    def test_authenticate_returns_owner_according_to_cookie_if_staff(self):
        request = self._create_request(cookie=self.user_to_impersonate)
        user, session = self.authenticator.authenticate(request)
        assert user == self.impersonated_user

    def test_authenticate_raises_permission_denied_if_not_staff(self):
        self.session.owner.staff = False
        self.session.owner.save()

        request = self._create_request(
            cookie=self.user_to_impersonate
        )

        with self.assertRaises(PermissionDenied):
            self.authenticator.authenticate(request)

    def test_authentication_fails_if_impersonated_user_doesnt_exist(self):
        self.user_to_impersonate = 'scoopy-doo'
        request = self._create_request(
            cookie=self.user_to_impersonate,
            service='github'
        )

        with self.assertRaises(AuthenticationFailed):
            self.authenticator.authenticate(request)

    def test_impersonation_with_non_github_provider(self):
        non_github_provider = 'bitbucket'
        self.impersonated_user.service = non_github_provider
        self.impersonated_user.save()

        request = self._create_request(
            cookie=self.user_to_impersonate,
            service=non_github_provider
        )

        user, session = self.authenticator.authenticate(request)
        assert user == self.impersonated_user
