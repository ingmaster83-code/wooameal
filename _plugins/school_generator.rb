require 'json'

module Jekyll
  module MealUtil
    def self.load_json(site, path)
      file = File.join(site.source, path)
      return [] unless File.exist?(file)
      JSON.parse(File.read(file, encoding: 'utf-8'))
    rescue => e
      Jekyll.logger.warn "MealGenerator:", "#{path} 로드 실패: #{e.message}"
      []
    end

    def self.rawdata_dir(site)
      File.join(site.source, '_rawdata')
    end
  end

  # ── 데이터 로드 (한 번만) ──────────────────────────────
  class SchoolDataGenerator < Generator
    safe true
    priority :highest

    def generate(site)
      return if site.data['school_all']

      dir = MealUtil.rawdata_dir(site)
      shard_files = Dir.glob(File.join(dir, 'schools_*.json'))
      all_schools = []
      by_do = Hash.new { |h, k| h[k] = [] }

      shard_files.each do |f|
        do_short = File.basename(f, '.json').sub('schools_', '')
        items = JSON.parse(File.read(f, encoding: 'utf-8'))
        by_do[do_short] = items
        all_schools.concat(items)
      end

      site.data['school_all'] = all_schools
      site.data['school_by_do'] = by_do
      Jekyll.logger.info "MealGenerator:", "총 #{all_schools.size}개 학교 로드 (#{by_do.size}개 시도)"
    end
  end

  # ── 시도 인덱스 페이지 ─────────────────────────────────
  class DoIndexPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      by_do = site.data['school_by_do'] || {}
      by_do.each do |do_short, schools|
        site.pages << DoIndexPage.new(site, do_short, schools)
      end
      Jekyll.logger.info "MealGenerator:", "시도 페이지 #{by_do.size}개 생성"
    end
  end

  class DoIndexPage < Page
    def initialize(site, do_short, schools)
      @site = site
      @base = site.source
      @dir  = "region/#{do_short}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'do.html')

      by_sigungu = Hash.new(0)
      schools.each { |s| by_sigungu[s['sigungu']] += 1 }
      sigungu_list = by_sigungu.map { |name, cnt| { 'name' => name, 'count' => cnt } }.sort_by { |s| -s['count'] }

      self.data['doShort'] = do_short
      self.data['sigunguList'] = sigungu_list
      self.data['totalCount'] = schools.size
      self.data['layout'] = 'do'
      self.data['title'] = "#{do_short} 학교 급식 식단표 — 시군구별 목록"
      self.data['description'] = "#{do_short} 지역 학교 #{schools.size}곳의 급식 식단표를 시군구별로 확인하세요."
    end
  end

  # ── 시군구 페이지 ──────────────────────────────────────
  class SigunguPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      by_do = site.data['school_by_do'] || {}
      count = 0
      by_do.each do |do_short, schools|
        grouped = Hash.new { |h, k| h[k] = [] }
        schools.each { |s| grouped[s['sigungu']] << s }
        grouped.each do |sigungu, list|
          site.pages << SigunguPage.new(site, do_short, sigungu, list)
          count += 1
        end
      end
      Jekyll.logger.info "MealGenerator:", "시군구 페이지 #{count}개 생성"
    end
  end

  class SigunguPage < Page
    def initialize(site, do_short, sigungu, schools)
      @site = site
      @base = site.source
      @dir  = "region/#{do_short}/#{sigungu}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'sigungu.html')

      self.data['doShort'] = do_short
      self.data['sigungu'] = sigungu
      self.data['schools'] = schools.sort_by { |s| s['schoolName'] }
      self.data['totalCount'] = schools.size
      self.data['layout'] = 'sigungu'
      self.data['title'] = "#{do_short} #{sigungu} 학교 급식 식단표 목록 (#{schools.size}곳)"
      self.data['description'] = "#{do_short} #{sigungu} 학교 #{schools.size}곳의 급식 식단표와 칼로리·영양정보를 확인하세요."
    end
  end

  # ── 개별 학교 상세 페이지 ──────────────────────────────
  class SchoolPageGenerator < Generator
    safe true
    priority :normal

    def generate(site)
      all_schools = site.data['school_all'] || []
      all_schools.each { |s| site.pages << SchoolPage.new(site, s) }
      Jekyll.logger.info "MealGenerator:", "학교 상세 페이지 #{all_schools.size}개 생성"
    end
  end

  class SchoolPage < Page
    def initialize(site, s)
      @site = site
      @base = site.source
      @dir  = "school/#{s['slug']}"
      @name = 'index.html'
      self.process(@name)
      self.read_yaml(File.join(@base, '_layouts'), 'school.html')

      meals = s['meals'] || []
      by_month = Hash.new { |h, k| h[k] = [] }
      meals.each do |m|
        next unless m['d'] && m['d'].length == 8
        ym = "#{m['d'][0,4]}-#{m['d'][4,2]}"
        by_month[ym] << m
      end
      month_list = by_month.keys.sort

      self.data.merge!(s)
      self.data['mealsByMonth'] = month_list.map { |ym| { 'ym' => ym, 'items' => by_month[ym] } }
      self.data['layout'] = 'school'
      self.data['title'] = "#{s['schoolName']} 급식 식단표 — 이번주 메뉴·칼로리 | #{s['doShort']} #{s['sigungu']}"
      cnt = meals.size
      extra = cnt > 0 ? "최근 #{cnt}건의 급식 메뉴와 칼로리 정보를 " : "급식 정보를 "
      self.data['description'] = "#{s['doShort']} #{s['sigungu']} #{s['schoolName']} 급식 식단표. #{extra}확인하세요."
    end
  end
end
