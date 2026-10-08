require 'json'
require 'date'

module Jekyll
  module SchedUtil
    WD = %w[일 월 화 수 목 금 토].freeze
    LEVELS = %w[초등학교 중학교 고등학교].freeze

    def self.d(s)
      Date.strptime(s, '%Y-%m-%d')
    end

    def self.md(s)
      x = d(s)
      "#{x.month}월 #{x.day}일"
    end

    def self.mdw(s)
      x = d(s)
      "#{x.month}월 #{x.day}일(#{WD[x.wday]})"
    end

    def self.short(s)
      x = d(s)
      "#{x.month}.#{x.day}"
    end

    def self.range_text(a, b, with_wd = false)
      f = with_wd ? method(:mdw) : method(:md)
      a == b ? f.call(a) : "#{f.call(a)} ~ #{f.call(b)}"
    end

    def self.range_compact(a, b)
      x = d(a); y = d(b)
      return "#{x.day}일(#{WD[x.wday]})" if a == b
      y.month == x.month ? "#{x.day}~#{y.day}일" : "#{x.month}.#{x.day}~#{y.month}.#{y.day}"
    end

    def self.days(a, b)
      (d(b) - d(a)).to_i + 1
    end

    def self.range_short(r)
      r ? "#{short(r[0])}~#{short(r[1])}" : nil
    end

    # 학교 요약(s)에서 화면용 텍스트를 만든다
    def self.texts(s)
      t = {}
      t['summer'] = "#{range_text(s['summer'][0], s['summer'][1])} (#{days(s['summer'][0], s['summer'][1])}일간)" if s['summer']
      t['winter'] = "#{range_text(s['winter'][0], s['winter'][1])} (#{days(s['winter'][0], s['winter'][1])}일간)" if s['winter']
      t['spring'] = range_text(s['spring'][0], s['spring'][1]) if s['spring']
      t['open1'] = mdw(s['open1']) if s['open1']
      t['open2'] = mdw(s['open2']) if s['open2']
      t['grad'] = mdw(s['grad']) if s['grad']
      t['end'] = mdw(s['end']) if s['end']
      t['exams'] = (s['exams'] || []).map { |a, b, n| { 'name' => n, 'text' => range_text(a, b) } }
      t['disc'] = (s['disc'] || []).map { |x| mdw(x) }
      t
    end

    def self.med(a)
      a.sort[a.size / 2]
    end

    # 학교들의 시작/종료일 분포를 "대체로 ~경" 문장으로
    def self.typical(starts, ends)
      return nil if starts.empty?
      s0 = starts.sort
      e0 = ends.sort
      tail = e0.empty? ? '' : "에 시작해 #{md(med(ends))}경 끝납니다"
      "대체로 #{md(med(starts))}경#{tail.empty? ? ' 시작합니다' : tail}(학교별 시작일 #{md(s0.first)}~#{md(s0.last)})"
    end

    def self.mode(list)
      return nil if list.empty?
      list.each_with_object(Hash.new(0)) { |v, h| h[v] += 1 }.max_by { |_, c| c }
    end
  end

  # ── 학교별 학사일정 페이지: /school/{slug}/schedule/ ─────────────────
  class ScheduleGenerator < Generator
    safe true
    priority :low

    def generate(site)
      sched = site.data['schedule'] || {}
      schools = site.data['school_all'] || []
      return if sched.empty?

      page_cnt = 0
      hubs = Hash.new { |h, k| h[k] = [] }   # [do, sigungu, level] => [{school, s}]
      schools.each do |sc|
        rec = sched[sc['code']]
        next unless rec && rec['ev'] && !rec['ev'].empty?
        site.pages << SchedulePage.new(site, sc, rec)
        page_cnt += 1
        s = rec['s'] || {}
        if SchedUtil::LEVELS.include?(sc['kind']) && (s['summer'] || s['winter'] || s['open2'])
          hubs[[sc['doShort'], sc['sigungu'], sc['kind']]] << { 'sc' => sc, 's' => s }
        end
      end

      ay = (sched.values.first || {})['ay']
      by_do = Hash.new { |h, k| h[k] = [] }
      hubs.each do |(do_short, sg, level), rows|
        site.pages << ScheduleHubPage.new(site, do_short, sg, level, rows, ay)
        by_do[do_short] << { 'sigungu' => sg, 'level' => level, 'count' => rows.size }
      end
      by_do.each { |do_short, list| site.pages << ScheduleDoPage.new(site, do_short, list, ay) }
      all_rows = hubs.values.flatten
      site.pages << ScheduleIndexPage.new(site, by_do, all_rows, ay)

      Jekyll.logger.info 'ScheduleGenerator:', "학교 일정 #{page_cnt}개 + 지역 허브 #{hubs.size}개 + 시도 #{by_do.size}개"
    end
  end

  class SchedulePage < Page
    def initialize(site, sc, rec)
      @site = site; @base = site.source
      @dir = "school/#{sc['slug']}/schedule"; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'schedule.html')

      s = rec['s'] || {}
      tx = SchedUtil.texts(s)
      ay = rec['ay']
      name = sc['schoolName']
      loc = "#{sc['doShort']} #{sc['sigungu']}"

      # 월별 전체 일정
      by_month = Hash.new { |h, k| h[k] = [] }
      noise = /\A(학급회의|동아리( ?활동)?|자율(\(자치\)|활동)?|창의적 ?체험활동|학생자치회의)\z/
      shown = rec['ev'].reject { |_, _, n| n =~ noise }.first(70)
      shown.each do |a, b, n|
        by_month[a[0, 7]] << { 'text' => SchedUtil.range_compact(a, b), 'name' => n }
      end
      months = by_month.keys.sort.map { |ym| { 'ym' => ym, 'label' => "#{ym[0, 4]}년 #{ym[5, 2].to_i}월", 'items' => by_month[ym] } }

      # FAQ (실제 날짜가 답에 들어간다)
      faq = []
      faq << { 'q' => "#{name} 여름방학은 언제부터인가요?", 'a' => "#{name}의 #{ay}학년도 여름방학은 #{tx['summer']}입니다.#{tx['open2'] ? " 2학기 개학일은 #{tx['open2']}#{s['open2est'] ? '(방학 종료 다음 등교일 기준 추정)' : ''}입니다." : ''}" } if tx['summer']
      faq << { 'q' => "#{name} 겨울방학은 언제인가요?", 'a' => "#{name}의 #{ay}학년도 겨울방학(학년말 방학 포함)은 #{tx['winter']}입니다." } if tx['winter']
      faq << { 'q' => "#{name} 개학일은 언제인가요?", 'a' => "#{name}의 #{ay}학년도 1학기 시업식·개학식은 #{tx['open1']}입니다.#{tx['open2'] ? " 2학기 개학일은 #{tx['open2']}입니다." : ''}" } if tx['open1']
      faq << { 'q' => "#{name} 시험기간은 언제인가요?", 'a' => "#{name}의 #{ay}학년도 시험 일정은 #{tx['exams'].map { |e| "#{e['name']} #{e['text']}" }.join(', ')}입니다." } unless tx['exams'].empty?
      faq << { 'q' => "#{name} 재량휴업일은 언제인가요?", 'a' => "#{name}의 #{ay}학년도 재량휴업일·개교기념일 등 휴업일은 #{tx['disc'].join(', ')}입니다." } unless tx['disc'].empty?

      parts = []
      parts << "여름방학 #{SchedUtil.range_text(*s['summer'])}" if s['summer']
      parts << "2학기 개학 #{SchedUtil.md(s['open2'])}" if s['open2']
      parts << "겨울방학 #{SchedUtil.range_text(*s['winter'])}" if s['winter']
      parts << "1학기 개학 #{SchedUtil.md(s['open1'])}" if s['open1'] && parts.size < 3
      parts << "#{s['exams'][0][2]} #{SchedUtil.range_text(s['exams'][0][0], s['exams'][0][1])}" if s['exams'] && !s['exams'].empty? && parts.size < 4
      desc_core = parts.empty? ? "월별 행사와 휴업일을 확인하세요." : parts.join(', ') + '. 월별 행사·재량휴업일 확인.'

      data.merge!(sc.reject { |k, _| %w[meals mealsByMonth].include?(k) })
      data['layout'] = 'schedule'
      data['ay'] = ay
      data['sTexts'] = tx
      data['sRaw'] = s
      data['months'] = months
      data['satCount'] = rec['sat']
      data['faq'] = faq
      data['evCount'] = rec['ev'].size
      data['title'] = "#{name} 학사일정 #{ay}학년도 — 개학일·방학·시험기간 | #{sc['doShort']} #{sc['sigungu']}"
      data['description'] = "#{loc} #{name} #{ay}학년도 학사일정. #{desc_core}"[0, 158]
    end
  end

  # ── 시군구 × 학교급 허브: /schedule/{do}/{sigungu}/{level}/ ──────────
  class ScheduleHubPage < Page
    def initialize(site, do_short, sg, level, rows, ay)
      @site = site; @base = site.source
      @dir = "schedule/#{do_short}/#{sg}/#{level}"; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'schedule_hub.html')

      list = rows.sort_by { |r| r['sc']['schoolName'] }.map do |r|
        s = r['s']; sc = r['sc']
        { 'name' => sc['schoolName'], 'slug' => sc['slug'],
          'summer' => SchedUtil.range_short(s['summer']), 'open2' => s['open2'] ? SchedUtil.short(s['open2']) : nil,
          'open2est' => s['open2est'], 'winter' => SchedUtil.range_short(s['winter']) }
      end
      sm = SchedUtil.mode(rows.map { |r| r['s']['summer'] }.compact)
      wm = SchedUtil.mode(rows.map { |r| r['s']['winter'] }.compact)
      om = SchedUtil.mode(rows.map { |r| r['s']['open2'] }.compact)
      sums = rows.map { |r| r['s']['summer'] }.compact
      wins = rows.map { |r| r['s']['winter'] }.compact
      opens = rows.map { |r| r['s']['open2'] }.compact
      summer_phrase = SchedUtil.typical(sums.map { |x| x[0] }, sums.map { |x| x[1] })
      winter_phrase = SchedUtil.typical(wins.map { |x| x[0] }, wins.map { |x| x[1] })
      open2_phrase = opens.empty? ? nil : "대체로 #{SchedUtil.md(SchedUtil.med(opens))}경(학교별 #{SchedUtil.md(opens.min)}~#{SchedUtil.md(opens.max)})"
      big = ->(m, n) { m && m[1] >= 3 && m[1] * 100 / n >= 40 }

      faq = []
      faq << { 'q' => "#{sg} #{level} 여름방학은 언제부터인가요?", 'a' => "#{do_short} #{sg} #{level}의 #{ay}학년도 여름방학은 #{summer_phrase}.#{big.call(sm, sums.size) ? " 가장 많은 학교(#{sm[1]}곳)는 #{SchedUtil.range_text(*sm[0])}입니다." : ''} 정확한 일정은 아래 표에서 학교를 선택해 확인하세요." } if summer_phrase
      faq << { 'q' => "#{sg} #{level} 2학기 개학일은 언제인가요?", 'a' => "#{sg} #{level}의 2학기 개학일은 #{open2_phrase}입니다.#{big.call(om, opens.size) ? " 가장 많은 학교(#{om[1]}곳)는 #{SchedUtil.mdw(om[0])}입니다." : ''}" } if open2_phrase
      faq << { 'q' => "#{sg} #{level} 겨울방학은 언제 시작하나요?", 'a' => "#{sg} #{level}의 겨울방학(학년말 방학)은 #{winter_phrase}.#{big.call(wm, wins.size) ? " 가장 많은 학교(#{wm[1]}곳)는 #{SchedUtil.range_text(*wm[0])}입니다." : ''}" } if winter_phrase

      data['layout'] = 'schedule_hub'
      data['doShort'] = do_short
      data['sigungu'] = sg
      data['level'] = level
      data['ay'] = ay
      data['rows'] = list
      data['count'] = rows.size
      data['summerPhrase'] = summer_phrase
      data['open2Phrase'] = open2_phrase
      data['winterPhrase'] = winter_phrase
      data['faq'] = faq
      bits = []
      bits << "여름방학 대체로 #{SchedUtil.md(SchedUtil.med(sums.map { |x| x[0] }))}~#{SchedUtil.md(SchedUtil.med(sums.map { |x| x[1] }))}" unless sums.empty?
      bits << "2학기 개학 #{SchedUtil.md(SchedUtil.med(opens))}경" unless opens.empty?
      bits << "겨울방학 #{SchedUtil.md(SchedUtil.med(wins.map { |x| x[0] }))}경부터" unless wins.empty?
      data['title'] = "#{sg} #{level} 방학·개학일 #{ay} — 학교별 여름방학·겨울방학 날짜 (#{rows.size}개교)"
      data['description'] = "#{do_short} #{sg} #{level} #{rows.size}곳의 #{ay}학년도 방학·개학일 비교.#{bits.empty? ? '' : ' ' + bits.join(', ') + '.'} 학교별 일정은 표에서 확인하세요."[0, 158]
    end
  end

  # ── 시도 허브: /schedule/{do}/ ───────────────────────────────────────
  class ScheduleDoPage < Page
    def initialize(site, do_short, list, ay)
      @site = site; @base = site.source
      @dir = "schedule/#{do_short}"; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'schedule_do.html')
      by_level = SchedUtil::LEVELS.map do |lv|
        { 'level' => lv, 'items' => list.select { |x| x['level'] == lv }.sort_by { |x| x['sigungu'] } }
      end
      data['layout'] = 'schedule_do'
      data['doShort'] = do_short
      data['ay'] = ay
      data['byLevel'] = by_level
      data['total'] = list.sum { |x| x['count'] }
      data['title'] = "#{do_short} 학교 방학·개학일 #{ay} — 시군구별 초중고 학사일정"
      data['description'] = "#{do_short} 초등학교·중학교·고등학교 #{data['total']}곳의 #{ay}학년도 여름방학·겨울방학·2학기 개학일을 시군구별로 확인하세요."[0, 158]
    end
  end

  # ── 전국 허브: /schedule/ ────────────────────────────────────────────
  class ScheduleIndexPage < Page
    def initialize(site, by_do, all_rows, ay)
      @site = site; @base = site.source
      @dir = 'schedule'; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'schedule_index.html')
      dos = by_do.map { |d, l| { 'name' => d, 'count' => l.sum { |x| x['count'] } } }.sort_by { |h| -h['count'] }
      sm = SchedUtil.mode(all_rows.map { |r| r['s']['summer'] }.compact)
      wm = SchedUtil.mode(all_rows.map { |r| r['s']['winter'] }.compact)
      om = SchedUtil.mode(all_rows.map { |r| r['s']['open2'] }.compact)
      data['layout'] = 'schedule_index'
      data['ay'] = ay
      data['dos'] = dos
      data['total'] = all_rows.size
      data['modeSummer'] = sm ? SchedUtil.range_text(*sm[0]) : nil
      data['modeWinter'] = wm ? SchedUtil.range_text(*wm[0]) : nil
      data['modeOpen2'] = om ? SchedUtil.mdw(om[0]) : nil
      data['title'] = "전국 학교 방학·개학일 #{ay}학년도 — 초중고 학사일정 찾기"
      data['description'] = "전국 초중고 #{all_rows.size}개교의 #{ay}학년도 여름방학·겨울방학·개학일·시험기간. 지역과 학교를 선택해 우리 학교 학사일정을 확인하세요."[0, 158]
    end
  end
end
