import { jsx as _jsx } from "react/jsx-runtime";
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pagination } from '../common/Pagination';
describe('Pagination', () => {
    it('renders nothing when everything fits on one page', () => {
        const { container } = render(_jsx(Pagination, { total: 10, limit: 50, offset: 0, onOffsetChange: vi.fn() }));
        expect(container).toBeEmptyDOMElement();
    });
    it('shows page info and disables Prev on the first page', () => {
        render(_jsx(Pagination, { total: 120, limit: 50, offset: 0, onOffsetChange: vi.fn() }));
        expect(screen.getByText(/Page 1 \/ 3/)).toBeInTheDocument();
        expect(screen.getByText('← Prev')).toBeDisabled();
        expect(screen.getByText('Next →')).toBeEnabled();
    });
    it('disables Next on the last page', () => {
        render(_jsx(Pagination, { total: 120, limit: 50, offset: 100, onOffsetChange: vi.fn() }));
        expect(screen.getByText(/Page 3 \/ 3/)).toBeInTheDocument();
        expect(screen.getByText('Next →')).toBeDisabled();
    });
    it('calls onOffsetChange with the next page offset', async () => {
        const user = userEvent.setup();
        const onOffsetChange = vi.fn();
        render(_jsx(Pagination, { total: 120, limit: 50, offset: 0, onOffsetChange: onOffsetChange }));
        await user.click(screen.getByText('Next →'));
        expect(onOffsetChange).toHaveBeenCalledWith(50);
    });
    it('never goes below offset 0 on Prev', async () => {
        const user = userEvent.setup();
        const onOffsetChange = vi.fn();
        render(_jsx(Pagination, { total: 120, limit: 50, offset: 20, onOffsetChange: onOffsetChange }));
        await user.click(screen.getByText('← Prev'));
        expect(onOffsetChange).toHaveBeenCalledWith(0);
    });
});
