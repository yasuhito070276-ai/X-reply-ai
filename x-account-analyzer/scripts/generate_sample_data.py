"""架空アカウントのサンプルデータを生成するスクリプト。

実在の人物・アカウントとは一切関係のない、テスト用の架空データです。
6ヶ月間で 0→1（初収益）を達成する架空のストーリーを再現しています。

実行方法:  python scripts/generate_sample_data.py
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "sample_posts.csv"

random.seed(42)

START = datetime(2025, 1, 6, 7, 30)

# フェーズごとの投稿テンプレート（架空の「在宅ワーク×デザイン」発信者）
PHASE_POSTS = {
    "opening": [
        "はじめまして。未経験からWebデザインを勉強中の会社員です。同じように挑戦する人と繋がりたくて発信を始めました。よろしくお願いします！",
        "今日からデザイン学習の記録を毎日投稿します。まずは1日1時間の勉強から。",
        "会社員をしながらスキルを身につけたい。時間がない中でどう学ぶかを試行錯誤していきます。",
        "おはようございます。朝活1日目。通勤前の30分でデザインの基礎を勉強しました。",
        "デザイン学習3日目。今日は配色の基本を学びました。むずかしいけど楽しい。",
    ],
    "knowhow": [
        "未経験からデザインを学ぶ人がまずやるべき3ステップ\n①基礎本を1冊だけ読む\n②毎日30分手を動かす\n③作ったものを公開する\n完璧を目指さないのがコツです。",
        "デザイン初心者がやりがちな失敗5選\n・フォントを使いすぎる\n・色を増やしすぎる\n・余白を怖がる\n・参考を見ない\n・完成させない\n私も全部やりました…",
        "無料で学べるデザイン教材まとめ。お金をかけなくても基礎は十分学べます。まずはここから始めるのがおすすめ。",
        "バナー模写の正しいやり方を解説します。ただ真似るだけじゃなく「なぜこの配置なのか」を言語化するのが上達の近道。",
        "配色に迷ったら60:30:10の法則。ベース60%、メイン30%、アクセント10%。これだけで一気に整います。",
        "デザインの勉強時間を捻出する方法。私は通勤電車の30分と昼休みの20分を固定枠にしています。すきま時間の積み重ねが一番強い。",
    ],
    "empathy": [
        "仕事から帰って勉強する気力がない日、ありますよね。私も今日はそうでした。そんな日は5分だけ参考デザインを眺めて寝ます。ゼロじゃなければOK。",
        "「未経験からじゃ無理」って言われると落ち込みますよね。でも実際に転身した人はみんな未経験からスタートしてる。大丈夫。",
        "SNSで同世代の活躍を見て焦る気持ち、痛いほどわかる。でも比べる相手は昨日の自分だけでいい。",
        "勉強が続かなくて自己嫌悪になる…そんな自分を責めないでください。続かない仕組みが悪いだけで、あなたが悪いわけじゃない。",
        "会社で疲れ果てて何もできない夜。そんな日々でも少しずつ前に進んでる。同じ状況の人、一緒にがんばりましょう。",
    ],
    "story": [
        "1年前の私は、残業続きで終電帰りの毎日でした。このままでいいのかと不安だった。あの日デザインの勉強を始めたことが、今の私のきっかけです。",
        "実は一度、勉強を3ヶ月サボって挫折しかけました。再開できたのは「完璧じゃなくていい」と思えたから。挫折の話も隠さず発信していきます。",
        "初めて作ったバナーを見返したら酷すぎて笑いました。でもこの積み重ねが今につながってる。過去の自分に感謝。",
    ],
    "education": [
        "デザインで一番大切なのは「誰に何を伝えるか」。ツールの使い方より先に、目的を考える習慣をつけるべきだと思う。",
        "スキル習得で重要なのは、インプット2割・アウトプット8割。作らないと上達しません。これが本質です。",
        "「センスがないから無理」は勘違い。デザインは知識とパターンの積み重ねで、センスは後からついてくる。学べば誰でも一定レベルには到達できます。",
        "続けるコツは意志力に頼らないこと。時間を固定し、環境を整え、記録を公開する。仕組みで解決するのが正解だと思う。",
    ],
    "achievement": [
        "ご報告。初めてポートフォリオを公開したところ、3件の感想をいただきました。小さな一歩だけど嬉しい。",
        "フォロワー500人を突破しました！いつも見てくださる皆さんのおかげです。ありがとうございます。",
        "毎日投稿90日達成しました。継続は裏切らない。",
        "先日作ったバナーがコンペで入選しました。未経験から8ヶ月、続けてきてよかった。",
    ],
    "interaction": [
        "今日もリプで交流してくださった皆さん、ありがとうございます！デザイン仲間が増えるのが一番嬉しい。",
        "【質問】皆さんが勉強でいちばん苦労していることは何ですか？リプで教えてください。今後の発信の参考にします。",
        "朝活仲間を募集します。平日朝7時から30分、一緒に作業しませんか？参加したい方はリプください。",
    ],
    "product_prep": [
        "最近DMで「学習手順を詳しく知りたい」という質問をたくさんいただきます。近日中に、私の学習ロードマップをnoteにまとめる準備をしています。",
        "noteの執筆進捗70%。未経験から8ヶ月分の学習記録とテンプレを全部詰め込みます。もう少しお待ちください。",
        "公式LINEを開設しました。登録者限定で「バナー模写チェックリスト」を無料配布します。プロフィールのリンクからどうぞ。",
        "メルマガも始めました。SNSでは書けない学習の裏話を週1で配信します。登録はプロフィールのリンクから。",
    ],
    "sales": [
        "【お知らせ】未経験からのデザイン学習ロードマップをnoteで公開しました。8ヶ月分の記録・教材リスト・模写テンプレ付きです。詳しくはプロフィールのリンクから。",
        "noteを公開して48時間。想像以上の反響をいただいています。感想を引用で紹介させてください。迷っている方の参考になれば。",
        "【残り3日】noteの早割価格は今週末まで。値上げ前にどうぞ。購入はプロフィールのリンクから。",
    ],
    "revenue": [
        "ご報告です。昨日公開したnoteが、ついに1件売れました！人生初収益です。金額は980円だけど、自分の経験がお金になった事実が嬉しくて泣きそう。0→1をやっと達成できました。買ってくださった方、本当にありがとうございます。",
    ],
    "expansion": [
        "noteの購入者が10名を超えました。感想も続々いただいています。ありがとうございます！",
        "初収益から2週間。売上は合計1万円を超えました。次はテンプレ集の第2弾を準備中です。",
        "購入者さんから「模写が続くようになった」と嬉しい報告。誰かの役に立てるって最高です。",
        "【御礼】noteが30部売れました。続編のご要望が多いので、動画版も検討しています。",
    ],
}

# (フェーズ, 開始日, 終了日, 週あたり投稿数, いいねの範囲)
SCHEDULE = [
    ("opening", 0, 21, 5, (1, 8)),
    ("knowhow", 21, 60, 6, (5, 30)),
    ("empathy", 45, 90, 4, (10, 50)),
    ("story", 60, 100, 2, (15, 80)),
    ("education", 80, 130, 5, (15, 60)),
    ("interaction", 90, 170, 3, (8, 40)),
    ("achievement", 100, 160, 2, (30, 120)),
    ("product_prep", 130, 152, 3, (20, 70)),
    ("sales", 152, 160, 3, (25, 90)),
    ("revenue", 157, 158, 7, (80, 150)),
    ("expansion", 160, 182, 4, (30, 100)),
]


def generate() -> list[dict]:
    posts = []
    post_id = 1900000000000000000
    followers = 30

    for phase, day_start, day_end, per_week, like_range in SCHEDULE:
        templates = PHASE_POSTS[phase]
        n_days = day_end - day_start
        n_posts = max(1, int(n_days / 7 * per_week))
        for i in range(n_posts):
            day = day_start + (n_days * i) // n_posts
            hour = random.choice([7, 8, 12, 19, 20, 21])
            dt = START + timedelta(days=day, hours=hour - 7, minutes=random.randint(0, 59))
            text = templates[i % len(templates)]
            likes = random.randint(*like_range)
            growth = 1 + day / 60  # 後半ほど反応が伸びる
            likes = int(likes * growth)
            replies = max(0, int(likes * random.uniform(0.05, 0.2)))
            reposts = max(0, int(likes * random.uniform(0.03, 0.15)))
            impressions = likes * random.randint(25, 60)
            followers += random.randint(0, 3 + int(likes / 20))
            posts.append({
                "post_id": str(post_id),
                "created_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "text": text,
                "impressions": impressions,
                "likes": likes,
                "replies": replies,
                "reposts": reposts,
                "bookmarks": int(likes * 0.3),
                "quotes": int(reposts * 0.2),
                "url": f"https://x.com/sample_creator/status/{post_id}",
                "media_type": random.choice(["", "", "image"]),
                "followers_count": followers,
            })
            post_id += random.randint(1000, 9999)

    posts.sort(key=lambda p: p["created_at"])
    return posts


def main() -> None:
    posts = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(posts[0].keys()))
        writer.writeheader()
        writer.writerows(posts)
    print(f"サンプルデータを生成しました: {OUT_PATH}（{len(posts)}件）")


if __name__ == "__main__":
    main()
