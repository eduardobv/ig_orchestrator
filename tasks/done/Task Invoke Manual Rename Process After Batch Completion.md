# Task: Invoke Manual Rename Process After Batch Completion

## Goal

Modify this script so that, after completing the full batch processing and generating the final report, it invokes the external Manual Rename Files process.

The external rename process is located in:

```text
D:\Archivos\Scripts\IG\ManualRenameFiles
```

This feature must be implemented as a post-processing step. It should run only after the current script has finished its own main work successfully, including the report generation.

---

## Context

This script is responsible for processing a batch and generating a report.

A separate script already exists for manually renaming and optionally moving files/folders. That rename script can be executed directly with command-line parameters, but it can also be wrapped in a `.bat` file.

The preferred approach for this feature is to call the `.bat` file instead of embedding all rename parameters directly inside this script.

Preferred command:

```text
D:\Archivos\Scripts\IG\ManualRenameFiles\MRF.bat
```

The `.bat` file contains the full command needed to run the rename process.

This keeps the current batch-processing script decoupled from the details of the rename script.

---

## Preferred Design Decision

Use the `.bat` file as the integration point.

Do not duplicate the full rename command inside this script unless there is already an established project pattern that requires direct Python invocation.

Reasoning:

* The rename process belongs to another script.
* The list of rename parameters is specific to the rename process, not to this batch script.
* Keeping the command inside `MRF.bat` makes it easier to change the rename process later without modifying this script.
* This avoids adding unrelated rename configuration into `batch.json`.
* The batch script should only know that a post-processing command must be executed after the report is generated.

---

## Do Not Add Rename Parameters to `batch.json`

Avoid adding the full rename parameters to `batch.json`.

The rename command is not part of the core batch configuration. It is a post-processing action that happens after the batch is finished.

The current script should not become responsible for managing these rename-specific values:

* `manualFolder`
* `consultFolders`
* `startNowDate`
* `ignoreConfig`
* `no-duplicated`
* `move-renamed`

Those values belong to the rename script or to the `MRF.bat` wrapper.

If configuration is needed in this script, keep it minimal and generic.

Recommended configuration concept:

```text
postProcessEnabled
postProcessCommand
```

or similar names consistent with the project style.

Example conceptual value:

```text
postProcessCommand = D:\Archivos\Scripts\IG\ManualRenameFiles\MRF.bat
```

Only add this to a config file if the existing project architecture already supports configurable post-processing commands.

If the project does not currently use this type of configuration, a clearly named constant or documented setting may be acceptable, following the project conventions.

---

## Required Behavior

After the script finishes processing the complete batch:

1. Complete all normal batch operations.
2. Generate the final report.
3. Confirm that the report generation step finished successfully.
4. Invoke the Manual Rename Files post-processing command.
5. Capture or display the result of that command according to the existing project logging style.
6. Finish with a clear message indicating whether the post-processing step succeeded or failed.

The external command must not run before the report is generated.

---

## Command to Execute

Preferred command:

```text
D:\Archivos\Scripts\IG\ManualRenameFiles\MRF.bat
```

The `.bat` file is expected to execute the rename script using a command equivalent to:

```text
python D:\Archivos\Scripts\IG\ManualRenameFiles\main.py --manualFolder "C:\Users\eduba\Downloads\DW\Telegram_Desktop" --consultFolders "G:\4K Stogram\00.FAVORITES" "G:\4K Stogram\00.MODELS-A" "G:\4K Stogram\00.MODELS-B" "G:\4K Stogram\00.MODELS-C" "G:\4K Stogram\00.MODELS-D" "G:\4K Stogram\03.LOW_ACTIVITY" --startNowDate "2026-07-05" --ignoreConfig --no-duplicated --move-renamed
```

Important:

* Do not hardcode this long command inside the current script if the `.bat` approach is available.
* Prefer invoking the `.bat` file.
* The `.bat` file is the owner of the rename-specific command-line parameters.

---

## Important Note About `pause`

The current `MRF.bat` may contain:

```text
pause
```

This can block the current script if the `.bat` file is executed from an automated process.

Codex should evaluate how this project is normally executed.

Recommended behavior:

* If this script is intended to run unattended, the invoked `.bat` should not block forever waiting for user input.
* If `pause` is only useful for manual execution, consider creating a second `.bat` for automation, for example:

  * `MRF.bat` for manual execution with `pause`
  * `MRF_auto.bat` for automated invocation without `pause`

Preferred automation command:

```text
D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat
```

If a new automation `.bat` is created, document the reason clearly.

Do not remove `pause` from the existing manual `.bat` if it is still useful for manual runs, unless the project owner clearly wants that behavior changed.

---

## Success and Failure Handling

The post-processing command should be treated as a separate final step.

If the main batch processing and report generation succeed, but the rename command fails:

* The script should report that the main batch completed successfully.
* The script should also report that the post-processing rename step failed.
* The error should be clear and actionable.
* Do not hide the failure.
* Do not make it look like the full process succeeded if the rename step failed.

Recommended final states:

```text
Batch processing: success
Report generation: success
Manual rename post-processing: success
```

or:

```text
Batch processing: success
Report generation: success
Manual rename post-processing: failed
```

If the existing project already has a result/report summary format, integrate this information there.

---

## When Not to Run the Post-Processing Step

The Manual Rename Files process must not be invoked if:

* The batch processing fails.
* The report generation fails.
* The script exits early due to validation errors.
* The script is running in a mode where post-processing is explicitly disabled, if such a mode exists or is added.

This prevents running the rename process after incomplete or invalid batch results.

---

## Logging Requirements

Follow the existing logging or console-output style used by the project.

At minimum, the script should log or print:

* That the batch processing finished.
* That the report was generated.
* That the Manual Rename Files post-processing step is starting.
* Which command or `.bat` file is being invoked.
* Whether the post-processing command completed successfully.
* The exit code if the command fails.
* Any relevant error output, if available.

Avoid excessive logging, but make failures easy to diagnose.

---

## Process Execution Requirements

Use a safe process execution approach.

The implementation should:

* Properly handle Windows paths with spaces.
* Avoid shell quoting problems.
* Preserve the working directory if the `.bat` file depends on it, or explicitly set the expected working directory.
* Wait for the post-processing command to finish before printing the final summary.
* Detect non-zero exit codes.
* Avoid silently ignoring failures.

If the project already has a utility for executing external commands, use that instead of introducing a new pattern.

---

## Configuration Recommendation

Do not add all rename parameters to `batch.json`.

If configuration is needed, add only generic post-processing configuration, for example:

```text
postProcessing:
  enabled: true
  command: D:\Archivos\Scripts\IG\ManualRenameFiles\MRF_auto.bat
```

Use the actual config format already used by this project.

The important point is that `batch.json` should not contain rename-specific business parameters unless the existing project architecture strongly requires it.

---

## Documentation Requirements

Follow the repository instructions in `AGENTS.md`.

Update `CHANGELOG.md` with a short entry describing this feature.

Also update any other project documentation that explains:

* How the batch script is executed.
* What happens after the report is generated.
* How to enable, disable, or modify post-processing.
* Which `.bat` file is called.

If a new automation `.bat` is created, document the difference between the manual and automation versions.

---

## Acceptance Criteria

The feature is complete when all of the following are true:

1. The current script completes the batch processing as before.
2. The final report is generated before invoking the rename process.
3. The Manual Rename Files process is invoked only after successful report generation.
4. The integration preferably calls a `.bat` file instead of duplicating the full rename command.
5. The script handles Windows paths correctly.
6. The script waits for the post-processing command to finish.
7. A successful post-processing run is clearly reported.
8. A failed post-processing run is clearly reported with a useful error message.
9. The rename process is not invoked if the batch or report generation fails.
10. Rename-specific parameters are not unnecessarily added to `batch.json`.
11. Any added configuration remains generic, such as a post-processing command path.
12. The implementation follows `AGENTS.md`.
13. `CHANGELOG.md` is updated.
14. Any relevant documentation is updated.
15. The current behavior remains unchanged when the post-processing step is disabled or not configured.
