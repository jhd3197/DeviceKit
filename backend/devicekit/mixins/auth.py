class AuthMixin:
    """API key and agent token authentication."""

    _api_key = ""
    _agent_tokens = []

    def configure_auth(self, api_key, agent_tokens):
        self._api_key = api_key
        self._agent_tokens = agent_tokens

    def validate_api_key(self, key):
        if not self._api_key:
            return True  # Auth disabled
        return key == self._api_key

    def validate_agent_token(self, token):
        if not self._agent_tokens:
            return True  # Agent auth disabled
        return token in self._agent_tokens
