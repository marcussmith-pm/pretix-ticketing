#
# This file is part of pretix.
#
# Copyright (C) 2025 pretix GmbH and contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation in version 3 of the License.
#
# ADDITIONAL TERMS APPLY: Pursuant to Section 7 of the GNU Affero General Public License, additional terms are
# applicable granting you additional permissions and placing additional restrictions on your usage of this software.
# Please refer to the pretix LICENSE file to obtain the full terms applicable to this work. If you did not receive
# this file, see <https://pretix.eu/about/en/license/>.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.  If not, see
# <https://www.gnu.org/licenses/>.

from django.urls import include, re_path

from pretix.plugins.poli import views

event_patterns = [
    re_path(r'^poli/', include([
        re_path(r'^return/(?P<order>[^/]+)/(?P<payment>[^/]+)/(?P<hash>[^/]+)/$', views.PoliReturnView.as_view(), name='return'),
        re_path(r'^cancel/(?P<order>[^/]+)/(?P<payment>[^/]+)/(?P<hash>[^/]+)/$', views.PoliCancelView.as_view(), name='cancel'),
        re_path(r'^webhook$', views.PoliWebhookView.as_view(), name='webhook'),
    ])),
]
