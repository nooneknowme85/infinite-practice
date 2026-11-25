import os
import json
import time
import argparse

from master_downloader import (
    BATCHES,
    NEET_ALLOWED_SUBJECTS,
    OUTPUT_ROOT,
    CONSECUTIVE_EMPTY_LIMIT,
    sanitize_filename,
    atomic_write_json,
    load_existing_questions,
    download_existing_releases,
    get_subjects,
    get_chapters,
    start_test,
    submit_test,
    get_solutions,
)

NEW_ONLY_ROOT = "new_questions_only"
REPORT_FILE = "recheck_report.json"


def fetch_batches_for_difficulty(
    batch_id,
    exam_category,
    chapter_id,
    class_id,
    subject_id,
    difficulty_level,
    target_missing,
    questions_dict,
    new_questions_dict,
    out_file,
    new_only_file,
    delay,
    label,
):
    """Fetch batches of 90 for a specific difficulty_level until exhausted or target met."""
    consecutive_empty = 0
    batch_idx = 1

    while target_missing > 0:
        print(f"    -> [{label}] Batch {batch_idx}: Requesting 90 Qs...", end=" ", flush=True)
        test_id, fallback_qs = start_test(
            batch_id, exam_category, chapter_id, class_id, subject_id,
            count=90, difficulty_level=difficulty_level
        )
        if not test_id:
            print("Failed to start test. Pausing 5s...")
            time.sleep(5)
            break

        time.sleep(delay)

        solutions_extracted = False
        if submit_test(test_id):
            time.sleep(1.5)
            solved_qs = get_solutions(test_id)
            if solved_qs:
                incoming_qs = solved_qs
                solutions_extracted = True
            else:
                incoming_qs = fallback_qs
        else:
            incoming_qs = fallback_qs

        new_added = 0
        for q in incoming_qs:
            qid = q.get("questionId")
            if qid and qid not in questions_dict:
                questions_dict[qid] = q
                new_questions_dict[qid] = q
                new_added += 1

        status_tag = "[Solutions & Video]" if solutions_extracted else "[Questions Only]"
        print(f"{status_tag} Received: {len(incoming_qs)} | NEW: {new_added} | Chapter New Total: {len(new_questions_dict)}")

        if new_added > 0:
            # Save updated full chapter AND new-questions-only delta file immediately
            atomic_write_json(out_file, list(questions_dict.values()))
            atomic_write_json(new_only_file, list(new_questions_dict.values()))
            target_missing -= new_added
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            print(f"       ↳ 0 new questions ({consecutive_empty}/{CONSECUTIVE_EMPTY_LIMIT} consecutive)")
            if consecutive_empty >= CONSECUTIVE_EMPTY_LIMIT:
                print(f"    [{label} Exhausted] {CONSECUTIVE_EMPTY_LIMIT} consecutive batches gave 0 new questions.")
                break

        batch_idx += 1
        time.sleep(delay)


def recheck_chapter(item, delay=2.5):
    """Recheck a single chapter using targeted difficulty queries, saving new questions only."""
    batch_name = item["batch_name"]
    batch_id = item["batch_id"]
    exam_category = item["exam_category"]
    subject_name = item["subject_name"]
    chapter = item["chapter"]
    chapter_id = chapter["chapterId"]
    class_id = chapter["classId"]
    chapter_name = chapter["englishName"]
    subject_id = chapter["subjectId"]

    out_file = item["out_file"]
    new_only_file = os.path.join(
        NEW_ONLY_ROOT,
        sanitize_filename(batch_name),
        sanitize_filename(subject_name),
        f"{sanitize_filename(chapter_name)}.json",
    )

    questions_dict, diff_counts = load_existing_questions(out_file)
    new_questions_dict = {}
    before_count = len(questions_dict)
    total_bank = item["total_bank"]

    easy_total = int(chapter.get("questionCountEasy") or 0)
    med_total = int(chapter.get("questionCountMedium") or 0)
    hard_total = int(chapter.get("questionCountHard") or 0)

    easy_miss = max(0, easy_total - diff_counts[1])
    med_miss = max(0, med_total - diff_counts[2])
    hard_miss = max(0, hard_total - diff_counts[3])

    print(f"\n=======================================================")
    print(f"RECHECK: [{batch_name}] > [{subject_name}] > [{chapter_name}]")
    print(f"Have: {before_count}/{total_bank} | Missing: {item['missing']}")
    print(f"Breakdown Missing -> Easy: {easy_miss} | Medium: {med_miss} | Hard: {hard_miss}")
    print(f"=======================================================")

    # Target only difficulty levels that are actually missing questions!
    targets = []
    if easy_miss > 0:
        targets.append(([1], easy_miss, "Easy"))
    if med_miss > 0:
        targets.append(([2], med_miss, "Medium"))
    if hard_miss > 0:
        targets.append(([3], hard_miss, "Hard"))

    if not targets:
        targets.append(([1, 2, 3], item["missing"], "All"))

    for diff_arr, miss_target, label in targets:
        if len(questions_dict) >= total_bank:
            break
        fetch_batches_for_difficulty(
            batch_id=batch_id,
            exam_category=exam_category,
            chapter_id=chapter_id,
            class_id=class_id,
            subject_id=subject_id,
            difficulty_level=diff_arr,
            target_missing=miss_target,
            questions_dict=questions_dict,
            new_questions_dict=new_questions_dict,
            out_file=out_file,
            new_only_file=new_only_file,
            delay=delay,
            label=label,
        )

    after_count = len(questions_dict)
    gained = len(new_questions_dict)
    print(f"  [RECHECK DONE] '{chapter_name}': {before_count} -> {after_count} (+{gained} NEW questions saved)\n")

    return {
        "batch": batch_name,
        "subject": subject_name,
        "chapter": chapter_name,
        "total_bank": total_bank,
        "before_count": before_count,
        "after_count": after_count,
        "new_questions_found": gained,
        "remaining_missing": max(0, total_bank - after_count),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Recheck missing questions in decreasing order and export ONLY new questions."
    )
    parser.add_argument(
        "--batch",
        type=str,
        default="all",
        help="Batch to recheck: '11th JEE', '12th JEE', '11th NEET', '12th NEET', or 'all'",
    )
    parser.add_argument(
        "--min-missing",
        type=int,
        default=1,
        help="Only recheck chapters missing at least this many questions (default: 1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.5,
        help="Delay in seconds between requests (default: 2.5)",
    )
    parser.add_argument(
        "--include-all-neet",
        action="store_true",
        default=False,
        help="Also recheck Physics & Chemistry for NEET (skipped by default since identical to JEE)",
    )
    parser.add_argument(
        "--download-releases",
        action="store_true",
        default=False,
        help="Download existing batch zips from GitHub Releases before scanning",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="GitHub repo 'owner/name' for --download-releases",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.download_releases:
        token = os.environ.get("GITHUB_TOKEN", "")
        download_existing_releases(args.repo, token, OUTPUT_ROOT)

    if args.batch.lower() == "all":
        target_batches = list(BATCHES.items())
    else:
        matched = [(k, v) for k, v in BATCHES.items() if k.lower() == args.batch.lower()]
        target_batches = matched if matched else list(BATCHES.items())

    print("Scanning local downloaded files vs live PW question bank counts...\n")
    queue = []

    for batch_name, batch_id in target_batches:
        exam_category, subjects = get_subjects(batch_id)
        if not subjects:
            continue
        time.sleep(1.0)

        for sub in subjects:
            sub_name = sub["englishName"]
            sub_id = sub["subjectId"]

            if "neet" in batch_name.lower() and not args.include_all_neet:
                if sub_name.strip().lower() not in NEET_ALLOWED_SUBJECTS:
                    continue

            chapters = get_chapters(batch_id, sub_id)
            time.sleep(1.0)

            for chap in chapters:
                total_bank = int(chap.get("questionCount") or 0)
                out_file = os.path.join(
                    OUTPUT_ROOT,
                    sanitize_filename(batch_name),
                    sanitize_filename(sub_name),
                    f"{sanitize_filename(chap['englishName'])}.json",
                )
                existing_dict, _ = load_existing_questions(out_file)
                existing_count = len(existing_dict)
                missing = max(0, total_bank - existing_count)

                if missing >= args.min_missing:
                    queue.append({
                        "batch_name": batch_name,
                        "batch_id": batch_id,
                        "exam_category": exam_category,
                        "subject_name": sub_name,
                        "chapter": chap,
                        "out_file": out_file,
                        "existing_count": existing_count,
                        "total_bank": total_bank,
                        "missing": missing,
                    })

    # Sort in DECREASING order of missing questions!
    queue.sort(key=lambda x: x["missing"], reverse=True)

    print("===================================================================")
    print(f"RECHECK QUEUE: {len(queue)} chapters missing >= {args.min_missing} questions")
    print("(Sorted in DECREASING order of missing questions)")
    print("===================================================================")
    for idx, item in enumerate(queue[:25], 1):
        print(
            f"  {idx:2d}. [Missing: {item['missing']:4d}] {item['batch_name']} > "
            f"{item['subject_name']} > {item['chapter']['englishName']} "
            f"({item['existing_count']}/{item['total_bank']})"
        )
    if len(queue) > 25:
        print(f"  ... and {len(queue) - 25} more chapters.")
    print("===================================================================\n")

    if not queue:
        print("All checked chapters are already 100% complete! Nothing to recheck.")
        return

    report = []
    total_new_found = 0

    for item in queue:
        res = recheck_chapter(item, delay=args.delay)
        report.append(res)
        total_new_found += res["new_questions_found"]
        atomic_write_json(REPORT_FILE, {
            "total_chapters_rechecked": len(report),
            "total_new_questions_found": total_new_found,
            "chapters": report,
        })
        time.sleep(1.5)

    print("===================================================================")
    print(f"RECHECK COMPLETE! Total NEW questions found: {total_new_found}")
    print(f"New questions saved in: '{NEW_ONLY_ROOT}/'")
    print(f"Full updated chapters saved in: '{OUTPUT_ROOT}/'")
    print(f"Summary report saved to: '{REPORT_FILE}'")
    print("===================================================================")


if __name__ == "__main__":
    main()
