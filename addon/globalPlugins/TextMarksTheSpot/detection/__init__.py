# -*- coding: UTF-8 -*-
# Detection dispatcher.
#
# Given a tree interceptor (or text info) and a context label from context.py,
# routes to the appropriate detector (web / email / form) and returns the
# detected content-start position, or None if no confident detection.

# TODO: from . import web, email, form
# TODO: def detect(treeInterceptor, ctx) -> Optional[Position]
