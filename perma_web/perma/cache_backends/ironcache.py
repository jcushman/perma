from django.conf import settings
from django.core.cache.backends.base import BaseCache, DEFAULT_TIMEOUT
from iron_cache import IronCache
import time


class DjangoIronCache(BaseCache):
    def __init__(self, location, params):
        options = params.get('OPTIONS', {})
        self.iron_cache = IronCache(
            options['IRON_CACHE_NAME'],
            project_id=options['IRON_CACHE_PROJECT_ID'],
            token=options['IRON_CACHE_TOKEN']
        )
        super(DjangoIronCache, self).__init__(params)

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT):
        """ Convert timeout to relative seconds from now. """
        return int(super(DjangoIronCache, self).get_backend_timeout(timeout) - time.time())

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None, ironcache_options=None):
        """
        Set a value in the cache if the key does not already exist. If
        timeout is given, that timeout will be used for the key; otherwise
        the default cache timeout will be used.

        TODO: Always returns None; should detect whether item was added and return true or false.
        """
        ironcache_options = ironcache_options.copy() if ironcache_options else {}
        ironcache_options.setdefault('add', True)
        self.set(key, value, timeout, version, ironcache_options)

    def get(self, key, default=None, version=None):
        """
        Fetch a given key from the cache. If the key does not exist, return
        default, which itself defaults to None.
        """
        key = self.make_key(key, version=version)
        val = self.iron_cache.get(key).value
        if val is None:
            return default
        return val

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None, ironcache_options=None):
        """
        Set a value in the cache. If timeout is given, that timeout will be
        used for the key; otherwise the default cache timeout will be used.
        """
        key = self.make_key(key, version=version)
        ironcache_options = ironcache_options.copy() if ironcache_options else {}
        if timeout:
            ironcache_options.setdefault('expires_in', self.get_backend_timeout(timeout))
        self.iron_cache.put(key, value, options=ironcache_options)

    def delete(self, key, version=None):
        """
        Delete a key from the cache, failing silently.
        """
        key = self.make_key(key, version=version)
        self.iron_cache.delete(key)

    def incr(self, key, delta=1, version=None):
        """
        Add delta to value in the cache.

        TODO: Should detect result and raise ValueError if the key does not exist.
        """
        key = self.make_key(key, version=version)
        self.iron_cache.increment(key, delta)

    def clear(self):
        """Remove *all* values from the cache at once."""
        raise NotImplementedError('subclasses of BaseCache must provide a clear() method')
