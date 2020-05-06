import logging
from base64 import b64decode
import hmac
import hashlib

from rest_framework import authentication
from rest_framework import exceptions

from codecov_auth.models import Session, Owner
from utils.config import get_config


log = logging.getLogger(__name__)


class CodecovSessionAuthentication(authentication.BaseAuthentication):
    """Authenticates based on the user cookie from the old codecov.io tornado system

    This Authenticator works based on the existing authentication method from the current/old
        codecov.io codebase. On tornado, the `set_secure_cookie` writes a base64 encoded
        value for the cookie, along with some metadata and a signature in the end.

    In this context we are not interested in the signature, since it will require a lot of
        code porting from tornado and it is not that beneficial for our code.

    Steps:

        The cookie comes in the format:

            2|1:0|10:1546487835|12:github-token|48:MDZlZDQwNmQtM2ZlNS00ZmY0LWJhYmEtMzQ5NzM5NzMyYjZh|f520039bc6cfb111e4cfc5c3e44fc4fa5921402918547b54383939da803948f4

        We first validate the string, to make sure the last field is the proper signature to the rest

        We then parse it and take the 5th pipe-delimited value

            48:MDZlZDQwNmQtM2ZlNS00ZmY0LWJhYmEtMzQ5NzM5NzMyYjZh

        This is the length + the field itself

            MDZlZDQwNmQtM2ZlNS00ZmY0LWJhYmEtMzQ5NzM5NzMyYjZh

        We base64 decode it and obtain

            06ed406d-3fe5-4ff4-baba-349739732b6a

        Which is the final token

    """

    def authenticate(self, request):
        authorization = request.META.get('HTTP_AUTHORIZATION', '')
        if not authorization or ' ' not in authorization:
            return None
        val, encoded_cookie = authorization.split(' ')
        if val != 'frontend':
            return None
        token = self.decode_token_from_cookie(encoded_cookie)
        try:
            session = Session.objects.get(token=token)
        except Session.DoesNotExist:
            raise exceptions.AuthenticationFailed('No such user')

        if "staff_user" in request.COOKIES and "service" in request.parser_context["kwargs"]:
            return self.attempt_impersonation(
                user=session.owner,
                username_to_impersonate=request.COOKIES["staff_user"],
                service=request.parser_context['kwargs']['service']
            )

        return (session.owner, session)

    def attempt_impersonation(self, user, username_to_impersonate, service):
        log.info((
            f"Impersonation attempted --"
            f" {user.username} impersonating {username_to_impersonate}"
        ))

        if not user.staff:
            log.info(f"Impersonation attempted by non-staff user: {user.username}")
            raise exceptions.PermissionDenied()

        try:
            impersonated_user = Owner.objects.get(
                service=service,
                username=username_to_impersonate
            )
        except Owner.DoesNotExist:
            log.warning((
                f"Unsuccessful impersonation of {username_to_impersonate}"
                f" on service {service}, user doesn't exist"
            ))
            raise exceptions.AuthenticationFailed(
                f"No such user to impersonate: {username_to_impersonate}"
            )
        log.info((
            f"Request impersonated -- successful "
            f"impersonation of {username_to_impersonate}, by {user.username}"
        ))
        return (impersonated_user, None)

    def decode_token_from_cookie(self, encoded_cookie):
        secret = get_config('setup', 'http', 'cookie_secret')
        cookie_fields = encoded_cookie.split('|')
        if len(cookie_fields) < 6:
            raise exceptions.AuthenticationFailed('No correct token format')
        cookie_value, cookie_signature = "|".join(cookie_fields[:5]) + "|", cookie_fields[5]
        expected_sig = self.create_signature(secret, cookie_value)
        if not hmac.compare_digest(cookie_signature, expected_sig):
            raise exceptions.AuthenticationFailed('Signature doesnt match')
        splitted = cookie_fields[4].split(':')
        if len(splitted) != 2:
            raise exceptions.AuthenticationFailed('No correct token format')
        _, encoded_token = splitted
        return b64decode(encoded_token).decode()

    def create_signature(self, secret: str, s: str) -> bytes:
        hash = hmac.new(secret.encode(), digestmod=hashlib.sha256)
        hash.update(s.encode())
        return hash.hexdigest()
