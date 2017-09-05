import scrapy
from pydispatch import dispatcher
from scrapy import signals
from amazon.helper import Helper
from amazon.items import KeywordRankingItem
from amazon.sql import RankingSql


class KeywordRankingSpider(scrapy.Spider):
    name = 'keyword_ranking'
    custom_settings = {
        'LOG_LEVEL': 'ERROR',
        'LOG_FILE': 'keyword_ranking.json',
        'LOG_ENABLED': True,
        'LOG_STDOUT': True
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = {}
        self.found = {}
        self.keyword_pool = {}
        dispatcher.connect(self.init_scrapy, signals.engine_started)
        dispatcher.connect(self.close_scrapy, signals.engine_stopped)

    def start_requests(self):
        for keyword, poll in self.keyword_pool.items():
            yield scrapy.Request(('https://www.amazon.com/s/?field-keywords=%s&t=' + Helper.random_str(10)) % keyword,
                                 self.load_first_page, meta={'items': poll})

    def parse(self, response):
        result_li = response.xpath('//li[@data-asin]')
        for item in response.meta['items']:
            if len(result_li) == 0:
                self.found[item['id']] = 'none'
            else:
                for result in result_li:
                    data_asin = result.xpath('./@data-asin').extract()[0]
                    if data_asin == item['asin']:
                        self.found[item['id']] = True
                        item = KeywordRankingItem()
                        data_id = result.xpath('./@id').extract()[0]
                        item_id = data_id.split('_')[1]
                        item['skwd_id'] = item['id']
                        item['rank'] = int(item_id) +1
                        yield item

                        break

    def load_first_page(self, response):
        page = response.css('#bottomBar span.pagnDisabled::text').extract()
        page = 1 if len(page) == 0 else int(page[0])
        page_num = 1
        while page_num <= page:
            # yield scrapy.Request(response.url + '&page=%s' % page_num, self.parse, meta={'asin': response.meta['item']['asin'],
            #                                                                              'skwd_id': response.meta['item']['id']})
            yield scrapy.Request(response.url + '&page=%s' % page_num, self.parse, meta={'items': response.meta['items']})
            page_num += 1

    def init_scrapy(self):
        self.items = RankingSql.fetch_keywords_ranking()
        for item in self.items:
            if item['keyword'] in self.keyword_pool.keys():
                self.keyword_pool[item['keyword']].append({'id': item['id'], 'asin': item['asin']})
            else:
                self.keyword_pool[item['keyword']] = [{'id': item['id'], 'asin': item['asin']}]
        self.found = {item['id']: False for item in self.items}

    def close_scrapy(self):
        for skwd_id, is_found in self.found.items():
            if is_found is not True:
                if is_found == 'none':
                    RankingSql.update_keywords_none_rank(skwd_id)
                else:
                    RankingSql.update_keywords_expire_rank(skwd_id)
