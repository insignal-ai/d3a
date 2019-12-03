"""
Copyright 2018 Grid Singularity
This file is part of D3A.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
from collections import namedtuple
from typing import Dict # noqa
import json

Clearing = namedtuple('Clearing', ('rate', 'energy'))


class Offer:
    def __init__(self, id, price, energy, seller, original_offer_price=None, seller_origin=None):
        self.id = str(id)
        self.real_id = id
        self.price = price
        self.original_offer_price = original_offer_price
        self.energy = energy
        self.seller = seller
        self.seller_origin = seller_origin

    def __repr__(self):
        return "<Offer('{s.id!s:.6s}', '{s.energy} kWh@{s.price}', '{s.seller} {rate}'>"\
            .format(s=self, rate=self.price / self.energy)

    def __str__(self):
        return "{{{s.id!s:.6s}}} [origin: {s.seller_origin}] " \
               "[{s.seller}]: {s.energy} kWh @ {s.price} @ {rate}"\
            .format(s=self, rate=self.price / self.energy)

    def to_JSON_string(self):
        return json.dumps(self.__dict__)

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id and \
            self.price == other.price and \
            self.original_offer_price == other.original_offer_price and \
            self.energy == other.energy and \
            self.seller == other.seller

    @classmethod
    def _csv_fields(cls):
        return 'id', 'rate [ct./kWh]', 'energy [kWh]', 'price [ct.]', 'seller'

    def _to_csv(self):
        rate = round(self.price / self.energy, 4)
        return self.id, rate, self.energy, self.price, self.seller


def offer_from_JSON_string(offer_string):
    offer_dict = json.loads(offer_string)
    real_id = offer_dict.pop('real_id')
    offer = Offer(**offer_dict)
    offer.real_id = real_id
    return offer


class Bid(namedtuple('Bid', ('id', 'price', 'energy', 'buyer', 'seller',
                             'original_bid_price', 'buyer_origin'))):
    def __new__(cls, id, price, energy, buyer, seller, original_bid_price=None,
                buyer_origin=None):
        # overridden to give the residual field a default value
        return super(Bid, cls).__new__(cls, str(id), price, energy, buyer, seller,
                                       original_bid_price, buyer_origin)

    def __repr__(self):
        return (
            "<Bid {{{s.id!s:.6s}}} [{s.buyer}] [{s.seller}] "
            "{s.energy} kWh @ {s.price} {rate}>".format(s=self, rate=self.price / self.energy)
        )

    def __str__(self):
        return (
            "{{{s.id!s:.6s}}} [origin: {s.buyer_origin}] [{s.buyer}] [{s.seller}] "
            "{s.energy} kWh @ {s.price} {rate}".format(s=self, rate=self.price / self.energy)
        )

    @classmethod
    def _csv_fields(cls):
        return 'id', 'rate [ct./kWh]', 'energy [kWh]', 'price [ct.]', 'buyer'

    def _to_csv(self):
        rate = round(self.price / self.energy, 4)
        return self.id, rate, self.energy, self.price, self.buyer

    def to_JSON_string(self):
        return json.dumps(self._asdict())


def bid_from_JSON_string(bid_string):
    bid_dict = json.loads(bid_string)
    return Bid(**bid_dict)


class TradeBidInfo(namedtuple('TradeBidInfo',
                              ('original_bid_rate', 'propagated_bid_rate',
                               'original_offer_rate', 'propagated_offer_rate',
                               'trade_rate'))):
    def to_JSON_string(self):
        return json.dumps(self._asdict())


def trade_bid_info_from_JSON_string(info_string):
    info_dict = json.loads(info_string)
    return TradeBidInfo(**info_dict)


class Trade(namedtuple('Trade', ('id', 'time', 'offer', 'seller',
                                 'buyer', 'residual', 'already_tracked',
                                 'offer_bid_trade_info', 'seller_origin', 'buyer_origin'))):
    def __new__(cls, id, time, offer, seller, buyer, residual=None,
                already_tracked=False, offer_bid_trade_info=None,
                seller_origin=None, buyer_origin=None):
        # overridden to give the residual field a default value
        return super(Trade, cls).__new__(cls, id, time, offer, seller, buyer, residual,
                                         already_tracked, offer_bid_trade_info, seller_origin,
                                         buyer_origin)

    def __str__(self):
        mark_partial = "(partial)" if self.residual is not None else ""
        return (
            "{{{s.id!s:.6s}}} [origin: {s.seller_origin} -> {s.buyer_origin}] "
            "[{s.seller} -> {s.buyer}] {s.offer.energy} kWh {p} @ {s.offer.price} {rate} "
            "{s.offer.id}".
            format(s=self, p=mark_partial, rate=round(self.offer.price / self.offer.energy, 8))
        )

    @classmethod
    def _csv_fields(cls):
        return (cls._fields[:2] + ('rate [ct./kWh]', 'energy [kWh]') +
                cls._fields[3:5])

    def _to_csv(self):
        rate = round(self.offer.price / self.offer.energy, 4)
        return self[:2] + (rate, self.offer.energy) + self[3:5]

    def to_JSON_string(self):
        trade_dict = self._asdict()
        trade_dict['offer'] = trade_dict['offer'].to_JSON_string()
        trade_dict['residual'] = trade_dict['residual'].to_JSON_string() \
            if trade_dict['residual'] is not None else None
        trade_dict['time'] = trade_dict['time'].isoformat()
        return json.dumps(trade_dict)


def trade_from_JSON_string(trade_string):
    trade_dict = json.loads(trade_string)
    trade_dict['offer'] = offer_from_JSON_string(trade_dict['offer'])
    if "residual" in trade_dict and trade_dict["residual"] is not None:
        trade_dict['residual'] = offer_from_JSON_string(trade_dict['residual'])

    return Trade(**trade_dict)


class BalancingOffer(Offer):

    def __repr__(self):
        return "<BalancingOffer('{s.id!s:.6s}', '{s.energy} kWh@{s.price}', '{s.seller} {rate}'>"\
            .format(s=self, rate=self.price / self.energy)

    def __str__(self):
        return "<BalancingOffer{{{s.id!s:.6s}}} [{s.seller}]: " \
               "{s.energy} kWh @ {s.price} @ {rate}>".format(s=self,
                                                             rate=self.price / self.energy)


class BalancingTrade(namedtuple('BalancingTrade', ('id', 'time', 'offer', 'seller',
                                                   'buyer', 'residual', 'offer_bid_trade_info',
                                                   'seller_origin', 'buyer_origin'))):
    def __new__(cls, id, time, offer, seller, buyer, residual=None, offer_bid_trade_info=None,
                seller_origin=None, buyer_origin=None):
        # overridden to give the residual field a default value
        return super(BalancingTrade, cls).__new__(cls, id, time, offer, seller,
                                                  buyer, residual, offer_bid_trade_info,
                                                  seller_origin, buyer_origin)

    def __str__(self):
        mark_partial = "(partial)" if self.residual is not None else ""
        return (
            "{{{s.id!s:.6s}}} [{s.seller} -> {s.buyer}] "
            "{s.offer.energy} kWh {p} @ {s.offer.price} {rate} {s.offer.id}".
            format(s=self, p=mark_partial, rate=self.offer.price / self.offer.energy)
        )

    @classmethod
    def _csv_fields(cls):
        return (cls._fields[:2] + ('rate [ct./kWh]', 'energy [kWh]') +
                cls._fields[3:5])

    def _to_csv(self):
        rate = round(self.offer.price / self.offer.energy, 4)
        return self[:2] + (rate, self.offer.energy) + self[3:5]


class MarketClearingState:
    def __init__(self):
        self.cumulative_offers = dict()  # type Dict[Datetime, dict()]
        self.cumulative_bids = dict()  # type Dict[Datetime, dict()]
        self.clearing = {}  # type: Dict[Datetime, tuple()]

    @classmethod
    def _csv_fields(cls):
        return 'time', 'rate [ct./kWh]'
