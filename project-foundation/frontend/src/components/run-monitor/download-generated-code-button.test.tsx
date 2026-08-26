import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DownloadGeneratedCodeButton } from '@/components/run-monitor/download-generated-code-button';

const downloadMock = vi.hoisted(() => ({
  downloadGeneratedCode: vi.fn(),
}));

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/services/api.service', () => ({
  runsService: { downloadGeneratedCode: downloadMock.downloadGeneratedCode },
}));

vi.mock('sonner', () => ({ toast: toastMock }));

describe('DownloadGeneratedCodeButton', () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // jsdom does not implement object URLs — polyfill + spy on anchor click.
    URL.createObjectURL = vi.fn(() => 'blob:mock') as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    clickSpy.mockRestore();
  });

  it('renders an enabled "Download Code" button when the project is complete', () => {
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    const button = screen.getByRole('button', { name: 'Download Code' });
    expect(button).toBeTruthy();
    expect(button).not.toBeDisabled();
    expect(button).toHaveProperty('title', 'Download the complete generated Playwright project');
  });

  it('is disabled with a "Generating…" label while the project is being generated', () => {
    render(<DownloadGeneratedCodeButton runId="run-1" ready={false} />);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(screen.getByText('Generating…')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Download Code' })).toBeNull();
  });

  it('triggers a download of the full project on click', async () => {
    downloadMock.downloadGeneratedCode.mockResolvedValueOnce(new Blob(['{}']));
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    fireEvent.click(screen.getByRole('button', { name: 'Download Code' }));

    await waitFor(() => {
      expect(downloadMock.downloadGeneratedCode).toHaveBeenCalledTimes(1);
      expect(downloadMock.downloadGeneratedCode).toHaveBeenCalledWith('run-1');
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(toastMock.success).toHaveBeenCalledWith('Generated Playwright project downloaded');
    });
  });

  it('shows a loading state and disables the button while downloading', async () => {
    let release!: (blob: Blob) => void;
    downloadMock.downloadGeneratedCode.mockReturnValue(
      new Promise<Blob>((resolve) => {
        release = resolve;
      })
    );
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    fireEvent.click(screen.getByRole('button', { name: 'Download Code' }));

    expect(screen.getByText('Downloading…')).toBeTruthy();
    expect(screen.getByRole('button')).toBeDisabled();
    expect(downloadMock.downloadGeneratedCode).toHaveBeenCalledTimes(1);

    release(new Blob(['{}']));
    await waitFor(() => expect(screen.getByText('Download Code')).toBeTruthy());
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  it('handles a missing / unavailable project with an error toast and restores the button', async () => {
    downloadMock.downloadGeneratedCode.mockRejectedValueOnce(
      new Error('Generated project not found for run: run-1')
    );
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    fireEvent.click(screen.getByRole('button', { name: 'Download Code' }));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith(
        'Download failed: Generated project not found for run: run-1'
      );
    });
    await waitFor(() => expect(screen.getByRole('button')).not.toBeDisabled());
    expect(screen.queryByText('Downloading…')).toBeNull();
    expect(downloadMock.downloadGeneratedCode).toHaveBeenCalledTimes(1);
  });

  it('handles network failure with an error toast', async () => {
    downloadMock.downloadGeneratedCode.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    fireEvent.click(screen.getByRole('button', { name: 'Download Code' }));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith('Download failed: Failed to fetch');
    });
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  it('prevents duplicate download requests on rapid repeated clicks', async () => {
    let release!: (blob: Blob) => void;
    downloadMock.downloadGeneratedCode.mockReturnValue(
      new Promise<Blob>((resolve) => {
        release = resolve;
      })
    );
    render(<DownloadGeneratedCodeButton runId="run-1" ready />);

    const button = screen.getByRole('button', { name: 'Download Code' });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(downloadMock.downloadGeneratedCode).toHaveBeenCalledTimes(1);

    release(new Blob(['{}']));
    await waitFor(() => expect(screen.getByText('Download Code')).toBeTruthy());
    expect(toastMock.success).toHaveBeenCalledTimes(1);
  });
});