import csv
import logging
import pathlib
import os
import plotly as py
import plotly.graph_objs as go
import pendulum
import shutil
from slugify import slugify

from d3a.constants import TIME_ZONE
from d3a.models.market.market_structures import Trade, BalancingTrade, Bid, Offer, BalancingOffer
from d3a.models.strategy.load_hours import LoadHoursStrategy, CellTowerLoadHoursStrategy
from d3a.models.strategy.predefined_load import DefinedLoadStrategy
from d3a.models.strategy.pv import PVStrategy
from d3a.models.strategy.storage import StorageStrategy
from d3a.models.area import Area

_log = logging.getLogger(__name__)

ENERGY_BUYER_SIGN_PLOTS = 1
ENERGY_SELLER_SIGN_PLOTS = -1 * ENERGY_BUYER_SIGN_PLOTS


def mkdir_from_str(directory: str, exist_ok=True, parents=True):
    out_dir = pathlib.Path(directory)
    out_dir.mkdir(exist_ok=exist_ok, parents=parents)
    return out_dir


class ExportAndPlot:

    def __init__(self, root_area: Area, path: str, subdir: str):
        self.trades = {}
        self.balancing_trades = {}
        self.stats = {}
        self.balancing_stats = {}
        self.buyer_trades = {}
        self.seller_trades = {}
        self.area = root_area

        try:
            if path is not None:
                path = os.path.abspath(path)
            self.directory = pathlib.Path(path or "~/d3a-simulation", subdir).expanduser()
            mkdir_from_str(str(self.directory.mkdir))
        except Exception as ex:
            _log.error("Could not open directory for csv exports: %s" % str(ex))
            return

        self.plot_dir = os.path.join(self.directory, 'plot')
        if not os.path.exists(self.plot_dir):
            os.makedirs(self.plot_dir)

        self.export()

    @staticmethod
    def _file_path(directory: dir, slug: str):
        file_name = ("%s.csv" % slug).replace(' ', '_')
        return directory.joinpath(file_name).as_posix()

    def export(self):
        """Wrapping function, executes all export and plotting functions"""

        self._export_area_with_children(self.area, self.directory)
        self._get_buyer_seller_trades(self.area)

        self.plot_trade_partner_cell_tower(self.area, self.plot_dir)
        self.plot_energy_profile(self.area, self.plot_dir)
        self.plot_all_unmatched_loads()
        self.plot_avg_trade_price(self.area, self.plot_dir)
        self.plot_ess_soc_history(self.area, self.plot_dir)

        self.move_root_plot_folder()

    def move_root_plot_folder(self):
        """
        Removes "grid" folder in self.plot_dir
        """
        old_dir = os.path.join(self.plot_dir, self.area.slug)
        if not os.path.isdir(old_dir):
            _log.error("PLOT ERROR: No plots were generated for {} under {}".
                       format(self.area.slug, self.plot_dir))
            return
        source = os.listdir(old_dir)
        for si in source:
            shutil.move(os.path.join(old_dir, si), self.plot_dir)
        shutil.rmtree(old_dir)

    def _export_area_with_children(self, area: Area, directory: dir):
        """
        Gets a self.stats and self.trades and writes them to csv files
        Runs _export_area_energy and _export_area_flat
        """
        if area.children:
            subdirectory = pathlib.Path(directory, area.slug.replace(' ', '_'))
            subdirectory.mkdir(exist_ok=True, parents=True)
            for child in area.children:
                self._export_area_with_children(child, subdirectory)
        self.stats[area.slug.replace(' ', '_')] = self._export_area_flat(area, directory, False)
        self.balancing_stats[area.slug.replace(' ', '_')] = \
            self._export_area_flat(area, directory, True)
        if area.children:
            self.trades[area.slug.replace(' ', '_')] = self._export_area_energy(area, directory)
            self.balancing_trades[area.slug.replace(' ', '_')] = \
                self._export_area_energy(area, directory, True)
            self._export_area_offers_bids(area, directory, "offers",
                                          Offer, "offers", area.past_markets)
            self._export_area_offers_bids(area, directory, "bids",
                                          Bid, "bids", area.past_markets)
            self._export_area_offers_bids(area, directory, "balancing-offers",
                                          BalancingOffer, "offers",
                                          area.past_balancing_markets)

    def _export_area_offers_bids(self, area, directory, file_suffix, offer_type,
                                 market_member, past_markets):
        """
        Exports files containing individual offers, bids or balancing offers
        (*-bids/offers/balancing-offers.csv files)
        return: dict[out_keys]
        """
        file_path = self._file_path(directory, f"{area.slug}-{file_suffix}")
        labels = ("slot",) + offer_type._csv_fields()
        try:
            with open(file_path, 'w') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(labels)
                for market in past_markets:
                    for offer in getattr(market, market_member).values():
                        row = (market.time_slot,) + offer._to_csv()
                        writer.writerow(row)
        except OSError:
            _log.exception("Could not export area balancing offers")

    def _export_area_energy(self, area: Area, directory: dir, balancing_area: bool = False):
        """
        Exports files containing individual trades  (*-trades.csv  files)
        return: dict[out_keys]
        """

        out_keys = ("sold_energy", "bought_energy")
        out_keys_ids = (5, 6)
        if balancing_area:
            file_path = self._file_path(directory, "{}-balancing-trades".format(area.slug))
            labels = ("slot",) + BalancingTrade._csv_fields()
            past_markets = area.past_balancing_markets
        else:
            file_path = self._file_path(directory, "{}-trades".format(area.slug))
            labels = ("slot",) + Trade._csv_fields()
            past_markets = area.past_markets

        try:
            with open(file_path, 'w') as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(labels)
                out_dict = dict((key, {}) for key in out_keys)
                for market in past_markets:
                    for trade in market.trades:
                        row = (market.time_slot,) + trade._to_csv()
                        writer.writerow(row)
                        for ii, ks in enumerate(out_keys):
                            node = slugify(row[out_keys_ids[ii]], to_lower=True)
                            if node not in out_dict[ks]:
                                out_dict[ks][node] = dict(
                                    (m.time_slot, 0) for m in area.past_markets)
                            out_dict[ks][node][market.time_slot] += row[4]
        except OSError:
            _log.exception("Could not export area trades")

        for ks in out_keys:
            out_dict[ks + "_lists"] = dict((ki, {}) for ki in out_dict[ks].keys())
            for node in out_dict[ks].keys():
                out_dict[ks + "_lists"][node]["slot"] = list(out_dict[ks][node].keys())
                out_dict[ks + "_lists"][node]["energy"] = list(out_dict[ks][node].values())
        return out_dict

    def _get_buyer_seller_trades(self, area: Area):
        """
        Determines the buy and sell rate of each leaf node
        """
        labels = ("slot", "rate [ct./kWh]", "energy [kWh]", "seller")
        for i, child in enumerate(area.children):
            for market in area.past_markets:
                for trade in market.trades:
                    buyer_slug = slugify(trade.buyer, to_lower=True)
                    seller_slug = slugify(trade.seller, to_lower=True)
                    if buyer_slug not in self.buyer_trades:
                        self.buyer_trades[buyer_slug] = dict((key, []) for key in labels)
                    if seller_slug not in self.seller_trades:
                        self.seller_trades[seller_slug] = dict((key, []) for key in labels)
                    else:
                        values = (market.time_slot, ) + \
                                 (round(trade.offer.price/trade.offer.energy, 4),
                                  (trade.offer.energy * -1),) + \
                                 (slugify(trade.seller, to_lower=True),)
                        for ii, ri in enumerate(labels):
                            self.buyer_trades[buyer_slug][ri].append(values[ii])
                            self.seller_trades[seller_slug][ri].append(values[ii])
            if child.children:
                self._get_buyer_seller_trades(child)

    def _export_area_flat(self, area: Area, directory: dir, balancing: bool):
        """
        Exports stats (*.csv files)
        """
        if balancing:
            data = ExportBalancingData(area)
            area_name = area.slug + "-balancing"
        else:
            data = ExportData.create(area)
            area_name = area.slug
        rows = data.rows()
        if rows:
            try:
                with open(self._file_path(directory, area_name), 'w') as csv_file:
                    writer = csv.writer(csv_file)
                    labels = data.labels()
                    writer.writerow(labels)
                    out_dict = dict((key, []) for key in labels)
                    for row in rows:
                        writer.writerow(row)
                        for ii, ri in enumerate(labels):
                            out_dict[ri].append(row[ii])
                return out_dict
            except Exception as ex:
                _log.error("Could not export area data: %s" % str(ex))

    def plot_trade_partner_cell_tower(self, area: Area, subdir: str):
        """
        Wrapper for _plot_trade_partner_cell_tower
        """
        key = "cell-tower"
        new_subdir = os.path.join(subdir, area.slug)
        for child in area.children:
            if child.slug == key:
                self._plot_trade_partner_cell_tower(child.slug, subdir)
            if child.children:
                self.plot_trade_partner_cell_tower(child, new_subdir)

    def _plot_trade_partner_cell_tower(self, load: str, plot_dir: str):
        """
        Plots trade partner pie graph for the sell tower.
        """
        higt = TradeHistory(self.buyer_trades, load)
        higt.arrange_data()
        mkdir_from_str(plot_dir)
        higt.plot_pie_chart("Energy Trade Partners for {}".format(load),
                            os.path.join(plot_dir, "energy_trade_partner_{}.html".format(load)))

    def plot_energy_profile(self, area: Area, subdir: str):
        """
        Wrapper for _plot_energy_profile
        """

        new_subdir = os.path.join(subdir, area.slug)
        self._plot_energy_profile(new_subdir, area.slug)
        for child in area.children:
            if child.children:
                self.plot_energy_profile(child, new_subdir)

    def _plot_energy_profile(self, subdir: str, market_name: str):
        """
        Plots history of energy trades
        """
        data = list()
        barmode = "relative"
        xtitle = 'Time'
        ytitle = 'Energy [kWh]'
        key = 'energy'
        title = 'Energy Trade Profile of {}'.format(market_name)
        data.extend(self._plot_energy_graph(self.trades, market_name, "sold_energy_lists",
                                            "-seller", key, ENERGY_SELLER_SIGN_PLOTS))
        data.extend(self._plot_energy_graph(self.trades, market_name, "bought_energy_lists",
                                            "-buyer", key, ENERGY_BUYER_SIGN_PLOTS))
        data.extend(self._plot_energy_graph(self.balancing_trades, market_name,
                                            "sold_energy_lists",
                                            "-balancing-seller", key, ENERGY_SELLER_SIGN_PLOTS))
        data.extend(self._plot_energy_graph(self.balancing_trades, market_name,
                                            "bought_energy_lists",
                                            "-balancing-buyer", key, ENERGY_BUYER_SIGN_PLOTS))
        if len(data) == 0:
            return
        if all([len(da.y) == 0 for da in data]):
            return

        plot_dir = os.path.join(self.plot_dir, subdir)
        mkdir_from_str(plot_dir)
        output_file = os.path.join(plot_dir,
                                   'energy_profile_{}.html'.format(market_name))
        BarGraph.plot_bar_graph(barmode, title, xtitle, ytitle, data, output_file)

    def _plot_energy_graph(self, trades, market_name, agent, agent_label, key, scale_value):
        internal_data = []
        for trader in trades[market_name][agent].keys():

            graph_obj = BarGraph(trades[market_name][agent][trader], key)
            graph_obj.graph_value(scale_value=scale_value)
            data_obj = go.Bar(x=list(graph_obj.umHours.keys()),
                              y=list(graph_obj.umHours.values()),
                              name=trader + agent_label)
            internal_data.append(data_obj)
        return internal_data

    def plot_all_unmatched_loads(self):
        """
        Plot unmatched loads of all loads in the configuration into one plot
        """
        unmatched_key = 'deficit [kWh]'
        data = list()
        root_name = self.area.slug
        title = 'Unmatched Loads for all devices in {}'.format(root_name)
        xtitle = 'Time'
        ytitle = 'Energy (kWh)'
        barmode = 'stack'
        load_list = [child_key for child_key in self.stats.keys()
                     if unmatched_key in self.stats[child_key].keys()]

        for li in load_list:
            graph_obj = BarGraph(self.stats[li], unmatched_key)
            if sum(graph_obj.dataset[unmatched_key]) < 1e-10:
                continue
            graph_obj.graph_value()
            data_obj = go.Bar(x=list(graph_obj.umHours.keys()),
                              y=list(graph_obj.umHours.values()),
                              name=li)
            data.append(data_obj)
        if len(data) == 0:
            return
        plot_dir = os.path.join(self.plot_dir)
        mkdir_from_str(plot_dir)
        output_file = os.path.join(plot_dir, 'unmatched_loads_{}.html'.format(root_name))
        BarGraph.plot_bar_graph(barmode, title, xtitle, ytitle, data, output_file)

    def plot_ess_soc_history(self, area, subdir):
        """
        Wrapper for _plot_ess_soc_history.
        """

        storage_key = 'charge [%]'
        new_subdir = os.path.join(subdir, area.slug)
        storage_list = [child.slug for child in area.children
                        if storage_key in self.stats[child.slug].keys()]
        if storage_list is not []:
            self._plot_ess_soc_history(storage_list, new_subdir, area.slug)
        for child in area.children:
            if child.children:
                self.plot_ess_soc_history(child, new_subdir)

    def _plot_ess_soc_history(self, storage_list: list, subdir: str, root_name: str):
        """
        Plots ess soc for each knot in the hierarchy
        """

        storage_key = 'charge [%]'
        data = list()
        barmode = "relative"
        title = 'ESS SOC ({})'.format(root_name)
        xtitle = 'Time'
        ytitle = 'Charge [%]'

        for si in storage_list:
            graph_obj = BarGraph(self.stats[si], storage_key)
            graph_obj.graph_value()
            data_obj = go.Scatter(x=list(graph_obj.umHours.keys()),
                                  y=list(graph_obj.umHours.values()),
                                  name=si)
            data.append(data_obj)
        if len(data) == 0:
            return
        plot_dir = os.path.join(self.plot_dir, subdir)
        mkdir_from_str(plot_dir)
        output_file = os.path.join(plot_dir, 'ess_soc_history_{}.html'.format(root_name))
        BarGraph.plot_bar_graph(barmode, title, xtitle, ytitle, data, output_file)

    def plot_avg_trade_price(self, area, subdir):
        """
        Wrapper for _plot_avg_trade_rate
        """
        if area.children:
            area_list = [area.slug]
            if area.parent:
                area_list.append(area.parent.slug)
            area_list += [ci.slug for ci in area.children]
            new_subdir = os.path.join(subdir, area.slug)
            self._plot_avg_trade_price(area_list, new_subdir)
            for child in area.children:
                self.plot_avg_trade_price(child, new_subdir)

    def _plot_avg_trade_price(self, area_list: list, subdir: str):
        """
        Plots average trade for the specified level of the hierarchy
        """
        data = list()
        barmode = 'stack'
        xtitle = "Time"
        ytitle = "Rate [ct./kWh]"
        key = 'avg trade rate [ct./kWh]'
        title = 'Average Trade Price {}'.format(area_list[0])
        for area_name in area_list:
            data.append(self._plot_avg_trade_graph(self.stats, area_name, key, area_name))
            if self.balancing_stats[area_name.lower()] is not None:
                area_name_balancing = area_name.lower() + "-demand-balancing-trades"
                data.append(self._plot_avg_trade_graph(self.balancing_stats, area_name,
                                                       'avg demand balancing trade rate [ct./kWh]',
                                                       area_name_balancing))
                area_name_balancing = area_name.lower() + "-supply-balancing-trades"
                data.append(self._plot_avg_trade_graph(self.balancing_stats, area_name,
                                                       'avg supply balancing trade rate [ct./kWh]',
                                                       area_name_balancing))

        if all([len(da.y) == 0 for da in data]):
            return
        plot_dir = os.path.join(self.plot_dir, subdir)
        mkdir_from_str(plot_dir)
        output_file = os.path.join(plot_dir, 'average_trade_price_{}.html'.format(area_list[0]))
        BarGraph.plot_bar_graph(barmode, title, xtitle, ytitle, data, output_file)

    def _plot_avg_trade_graph(self, stats, area_name, key, label):
        graph_obj = BarGraph(stats[area_name.lower()], key)
        graph_obj.graph_value()
        data_obj = go.Scatter(x=list(graph_obj.umHours.keys()),
                              y=list(graph_obj.umHours.values()),
                              name=label.lower())
        return data_obj


class ExportData:
    def __init__(self, area):
        self.area = area

    @staticmethod
    def create(area):
        return ExportUpperLevelData(area) if len(area.children) > 0 else ExportLeafData(area)


class ExportUpperLevelData(ExportData):
    def __init__(self, area):
        super(ExportUpperLevelData, self).__init__(area)

    def labels(self):
        return ['slot',
                'avg trade rate [ct./kWh]',
                'min trade rate [ct./kWh]',
                'max trade rate [ct./kWh]',
                '# trades',
                'total energy traded [kWh]',
                'total trade volume [EURO ct.]']

    def rows(self):
        return [self._row(m.time_slot, m) for m in self.area.past_markets]

    def _row(self, slot, market):
        return [slot,
                market.avg_trade_price,
                market.min_trade_price,
                market.max_trade_price,
                len(market.trades),
                sum(trade.offer.energy for trade in market.trades),
                sum(trade.offer.price for trade in market.trades)]


class ExportBalancingData:
    def __init__(self, area):
        self.area = area

    def labels(self):
        return ['slot',
                'avg supply balancing trade rate [ct./kWh]',
                'avg demand balancing trade rate [ct./kWh]']

    def rows(self):
        return [self._row(m.time_slot, m) for m in self.area.past_balancing_markets]

    def _row(self, slot, market):
        return [slot,
                market.avg_supply_balancing_trade_rate,
                market.avg_demand_balancing_trade_rate]


class ExportLeafData(ExportData):
    def __init__(self, area):
        super(ExportLeafData, self).__init__(area)

    def labels(self):
        return ['slot',
                'energy traded [kWh]',
                ] + self._specific_labels()

    def _specific_labels(self):
        if isinstance(self.area.strategy, StorageStrategy):
            return ['bought [kWh]', 'sold [kWh]', 'charge [kWh]', 'offered [kWh]', 'charge [%]']
        elif isinstance(self.area.strategy, LoadHoursStrategy):
            return ['desired energy [kWh]', 'deficit [kWh]']
        elif isinstance(self.area.strategy, PVStrategy):
            return ['produced to trade [kWh]', 'not sold [kWh]', 'forecast / generation [kWh]']
        return []

    def rows(self):
        return [self._row(m.time_slot, m) for m in self.area.parent.past_markets]

    def _traded(self, market):
        return market.traded_energy[self.area.name]

    def _row(self, slot, market):
        return [slot,
                self._traded(market),
                ] + self._specific_row(slot, market)

    def _specific_row(self, slot, market):
        if isinstance(self.area.strategy, (StorageStrategy)):
            s = self.area.strategy.state
            return [market.bought_energy(self.area.name),
                    market.sold_energy(self.area.name),
                    s.charge_history_kWh[slot],
                    s.offered_history[slot],
                    s.charge_history[slot]]
        elif isinstance(self.area.strategy, (LoadHoursStrategy, DefinedLoadStrategy,
                                             DefinedLoadStrategy, CellTowerLoadHoursStrategy)):
            desired = self.area.strategy.state.desired_energy_Wh[slot] / 1000
            return [desired, self._traded(market) + desired]
        elif isinstance(self.area.strategy, PVStrategy):
            produced = market.actual_energy_agg.get(self.area.name, 0)
            return [produced,
                    round(produced - self._traded(market), 4),
                    self.area.strategy.energy_production_forecast_kWh[slot] *
                    self.area.strategy.panel_count
                    ]
        return []


class BarGraph:
    def __init__(self, dataset: dict, key: str):
        self.key = key
        self.dataset = dataset
        self.umHours = dict()

    def graph_value(self, scale_value=1):
        try:
            self.dataset[self.key]
        except KeyError:
            pass
        else:
            for de in range(len(self.dataset[self.key])):
                if self.dataset[self.key][de] != 0:
                    if self.dataset[self.key][de] == "-":
                        self.umHours[self.dataset['slot'][de]] = 0.0
                    else:
                        self.umHours[self.dataset['slot'][de]] = \
                            round(self.dataset[self.key][de], 5) * scale_value

    @staticmethod
    def modify_time_axis(data: dict, title: str):
        """
        Changes timezone of pendulum x-values to 'UTC' and determines the list of days
        in order to return the time_range for the plot
        """
        day_set = set()
        for di in range(len(data)):
            time_list = data[di]["x"]
            for ti in time_list:
                day_set.add(pendulum.datetime(ti.year, ti.month, ti.day, tz=TIME_ZONE))

        day_list = sorted(list(day_set))
        if len(day_list) == 0:
            raise ValueError("There is no time information in plot {}".format(title))

        start_time = pendulum.datetime(day_list[0].year, day_list[0].month, day_list[0].day,
                                       0, 0, 0, tz=TIME_ZONE)
        end_time = pendulum.datetime(day_list[-1].year, day_list[-1].month, day_list[-1].day,
                                     23, 59, 59, tz=TIME_ZONE)

        return [start_time, end_time], data

    @classmethod
    def plot_bar_graph(cls, barmode: str, title: str, xtitle: str, ytitle: str, data, iname: str):
        try:
            time_range, data = cls.modify_time_axis(data, title)
        except ValueError:
            return

        layout = go.Layout(
            barmode=barmode,
            title=title,
            yaxis=dict(
                title=ytitle
            ),
            xaxis=dict(
                title=xtitle,
                range=time_range
            ),
            font=dict(
                size=16
            ),
            showlegend=True
        )

        fig = go.Figure(data=data, layout=layout)
        py.offline.plot(fig, filename=iname, auto_open=False)


class TradeHistory:
    def __init__(self, dataset: dict, key: str):
        self.key = key
        self.dataset = dataset
        self.trade_history = dict()

    def arrange_data(self):
        try:
            self.dataset[self.key]
        except KeyError:
            pass
        else:
            for ii, ki in enumerate(self.dataset[self.key]["seller"]):
                if ki in self.trade_history.keys():
                    self.trade_history[ki] += abs(self.dataset[self.key]["energy [kWh]"][ii])
                else:
                    self.trade_history[ki] = abs(self.dataset[self.key]["energy [kWh]"][ii])

    def plot_pie_chart(self, title, filename):
        fig = {
            "data": [
                {
                    "values": list(),
                    "labels": list(),
                    "type": "pie"
                }],
            "layout": {
                "title": title,
                "font": {"size": 16
                         }
            }
        }
        for key, value in self.trade_history.items():
            fig["data"][0]["values"].append(value)
            fig["data"][0]["labels"].append(key)

        py.offline.plot(fig, filename=filename, auto_open=False)
