"""ルールベース分析のテスト。"""
from services import analyzer


def test_classify_knowhow_post():
    result = analyzer.classify_post("初心者向けのバナー作成のコツを3ステップで解説します。やり方は簡単です。")
    assert result["category_primary"] == "ノウハウ"
    assert 0 <= result["confidence"] <= 1
    assert result["reason"]


def test_classify_sales_post():
    result = analyzer.classify_post("本日から販売開始！先着10名は特典付きです。購入はこちらから。")
    assert result["category_primary"] == "販売"


def test_classify_secondary_max_two():
    result = analyzer.classify_post(
        "フォロワー1000人達成しました！感謝です。コツはプロフィールのリンクにまとめました。フォローお願いします。"
    )
    assert len(result["category_secondary"]) <= 2
    assert result["category_primary"] != ""


def test_classify_no_keywords():
    result = analyzer.classify_post("あ")
    assert result["category_primary"] == "その他"


def test_revenue_candidate_detected():
    text = "ご報告です。noteがついに1件売れました！人生初収益です。0→1をやっと達成できました。"
    result = analyzer.detect_revenue_candidate(text)
    assert result["is_revenue_candidate"] is True
    assert result["revenue_confidence"] >= 0.5
    assert "キーワード" in result["revenue_reason"]


def test_revenue_howto_not_confirmed():
    """「初収益を出す方法」のようなノウハウ解説は確信度が下がる。"""
    howto = analyzer.detect_revenue_candidate("初収益を出す方法を3ステップで解説します。このコツを知れば誰でもできます。")
    report = analyzer.detect_revenue_candidate("ついに初収益が発生しました！嬉しい！980円ですが大きな一歩です。")
    assert howto["revenue_confidence"] < report["revenue_confidence"]


def test_no_revenue_keywords():
    result = analyzer.detect_revenue_candidate("今日はいい天気ですね。")
    assert result["is_revenue_candidate"] is False
    assert result["revenue_confidence"] == 0.0


def test_extract_features_line_and_note():
    text = "公式LINEを開設しました。登録者限定で配布します。詳しくはこちら https://example.com"
    f = analyzer.extract_features(text)
    assert f["has_line"] is True
    assert f["has_external_link"] is True


def test_extract_sales_numbers():
    f = analyzer.extract_features("今月の売上は5万円でした。フォロワー1,200人になりました。")
    assert f["sales_numbers"] != ""
    assert f["follower_numbers"] != ""


def test_analyze_posts_df(sample_posts_df):
    result = analyzer.analyze_posts_df(sample_posts_df)
    assert len(result) == len(sample_posts_df)
    assert "category_primary" in result.columns
    # 初収益投稿（post_id=6）が候補として検出される
    rev = result[result["post_id"] == "6"]
    assert rev["is_revenue_candidate"].iloc[0] == True  # noqa: E712
