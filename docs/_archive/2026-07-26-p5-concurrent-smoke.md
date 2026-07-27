# P5 concurrent-run smoke log

- LW cycle 1: LW repo was clean at HEAD 18b7ddda (only untracked style.jpg/style2.jpg) and this smoke log did not exist yet, so cycle 1 created it with no sign of a concurrent writer. (head 18b7ddda)
- LW cycle 2: controller.log shows one loop process (pid 23320, run_id 87ca8ca0) alternating slot 1.lock then 0.lock, with Global\LWRC_GEMINI acquired and released inside 17s and no recorded wait, so no concurrent-run overlap was visible this cycle. (head 646263d0)
